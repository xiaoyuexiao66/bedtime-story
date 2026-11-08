"""本地故事服务：网页界面 + 故事生成 + 声音合成。

启动： python app.py
然后浏览器打开 http://localhost:8000
同 Wi-Fi 的 iPhone 打开 http://<电脑的局域网IP>:8000
"""

import logging
import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

import config
import db
import asr_engine
import story_llm
import tts_engine

config.load_dotenv()
config.refresh()
config.ensure_dirs()
db.init_db()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bedtime")

# 合成任务放在后台线程里跑，前端轮询进度。
# 避免把 2 分钟的合成塞进一个 HTTP 请求，被 Safari 的 60 秒超时掐断。
_tts_jobs = {}
_tts_jobs_lock = threading.Lock()


def _normalize_voice_name(name) -> str:
    """把声音名字统一格式，方便和模型返回的名字对上。"""
    name = str(name or "").strip().strip("\"'“”‘’ ")
    for suffix in ("的声音", "声音"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    return name


def _find_voice_by_name(name, voices):
    """按名字找声音：先精确匹配，再退一步做包含匹配。"""
    target = _normalize_voice_name(name)
    if not target:
        return None
    for voice in voices:
        if _normalize_voice_name(voice["name"]) == target:
            return voice
    for voice in voices:
        voice_name = _normalize_voice_name(voice["name"])
        if voice_name and (voice_name in target or target in voice_name):
            return voice
    return None


def _warm_asr():
    """启动后在后台加载识别模型，孩子第一次点按钮时就不用干等 3~4 秒。"""
    try:
        asr_engine.get_asr().warm_up()
        log.info("语音识别模型已就绪")
    except Exception as e:
        log.info("语音识别暂时不可用：%s", e)


threading.Thread(target=_warm_asr, daemon=True).start()

app = FastAPI(title="睡前故事机")
app.mount("/static", StaticFiles(directory=str(config.ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(config.ROOT / "templates"))


@app.get("/")
def index(request: Request):
    engine = None
    try:
        engine = tts_engine.get_engine().name
    except tts_engine.TTSError:
        pass
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "stories": db.list_stories(),
            "voices": db.list_voices(),
            "default_voice": db.get_default_voice(),
            "engine": engine,
        },
    )


@app.get("/story/{story_id}")
def story_page(request: Request, story_id: int):
    story = db.get_story(story_id)
    if not story:
        raise HTTPException(404, "故事不存在")
    return templates.TemplateResponse(
        "story.html",
        {
            "request": request,
            "story": story,
            "voices": db.list_voices(),
        },
    )


@app.get("/api/health")
def health():
    engine = "none"
    try:
        engine = tts_engine.get_engine().name
    except tts_engine.TTSError:
        pass
    asr_ok = False
    try:
        asr_ok = asr_engine.get_asr().available()
    except asr_engine.ASRError:
        pass
    return {"ok": True, "tts_engine": engine, "asr": asr_ok}


@app.get("/api/stories")
def api_list_stories():
    return db.list_stories()


@app.post("/api/stories")
def api_create_story(payload: dict):
    topic = str(payload.get("topic") or "").strip()
    # 孩子对着麦克风说的原话；有它时，模型会顺便判断用哪个声音
    utterance = str(payload.get("utterance") or "").strip()
    try:
        age = int(payload.get("age") or 4)
    except (TypeError, ValueError):
        age = 4
    age = max(1, min(12, age))

    voices = db.list_voices()
    try:
        result = story_llm.generate_story(
            topic,
            age,
            voice_names=[v["name"] for v in voices],
            utterance=utterance or None,
        )
    except story_llm.StoryError as e:
        raise HTTPException(400, str(e))

    # 模型听出了声音要求就用它；没听出来（或名字对不上）就用默认声音
    voice = _find_voice_by_name(result.get("voice_name"), voices)
    if not voice:
        voice = db.get_default_voice()

    story_id = db.add_story(
        result["title"],
        result["body"],
        result["topic"],
        age,
        voice["id"] if voice else None,
    )
    log.info(
        "生成故事 #%s 《%s》，声音：%s",
        story_id,
        result["title"],
        voice["name"] if voice else "（还没有声音）",
    )
    story = db.get_story(story_id)
    story["voice_name"] = voice["name"] if voice else None
    return story


@app.get("/api/voices")
def api_list_voices():
    default = db.get_default_voice()
    voices = db.list_voices()
    for voice in voices:
        voice["is_default"] = bool(default and voice["id"] == default["id"])
    return voices


@app.post("/api/settings/default-voice")
def api_set_default_voice(payload: dict):
    """记住“孩子没说用谁讲时，默认用哪个声音”。"""
    voice_id = payload.get("voice_id")
    try:
        voice = db.get_voice(int(voice_id)) if voice_id not in (None, "") else None
    except (TypeError, ValueError):
        voice = None
    if not voice:
        raise HTTPException(400, "选择的声音不存在，请刷新页面后重试")
    db.set_setting("default_voice_id", voice["id"])
    log.info("默认声音设为 %s", voice["name"])
    return {"ok": True, "default_voice": voice}


@app.post("/api/transcribe")
def api_transcribe(file: UploadFile = File(...)):
    """把小孩说的一句话转成文字，用作故事主题。"""
    raw = file.file.read()
    if len(raw) < 1000:
        raise HTTPException(400, "录音太短，没听清，再来一次吧")
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise HTTPException(400, "只支持 WAV 格式的录音")
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(400, "录音太长了，说短一点吧")

    tmp_dir = config.DATA_DIR / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f"asr_{int(time.time() * 1000)}.wav"
    tmp.write_bytes(raw)
    try:
        engine = asr_engine.get_asr()
        text = engine.transcribe(tmp)
    except asr_engine.ASRError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        log.exception("语音识别失败")
        raise HTTPException(500, f"语音识别失败：{e}")
    finally:
        tmp.unlink(missing_ok=True)

    if not text:
        raise HTTPException(400, "没听清，再靠近一点说一次好吗？")
    log.info("语音识别：%s", text)
    return {"text": text}


@app.post("/api/voices")
def api_add_voice(
    name: str = Form("妈妈"),
    ref_text: str = Form(""),
    file: UploadFile = File(...),
):
    raw = file.file.read()
    if len(raw) < 1000:
        raise HTTPException(400, "录音太短或文件无效，请重新录一段 3~10 秒的声音")
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise HTTPException(400, "只支持 WAV 格式的录音")

    # 文件名只保留 ASCII，避免跨平台和 URL 编码问题；中文名字仍保存在数据库里
    safe_name = (
        "".join(c for c in name.strip() if c.isascii() and (c.isalnum() or c in "-_"))
        or "voice"
    )
    filename = f"voice_{int(time.time())}_{safe_name}.wav"
    path = config.VOICE_DIR / filename
    path.write_bytes(raw)

    voice_id = db.add_voice(name.strip() or "妈妈", str(path), ref_text.strip())
    log.info("新增声音 #%s %s", voice_id, filename)
    return db.get_voice(voice_id)


def _run_tts_job(story_id: int, voice: dict, engine):
    """后台合成整段故事，结果放进 _tts_jobs 供前端查询。"""
    story = db.get_story(story_id)
    out_path = config.AUDIO_DIR / f"story_{story_id}.wav"
    started = time.time()
    try:
        engine.synthesize(
            story["body"],
            voice["wav_path"],
            voice["ref_text"],
            out_path,
        )
        db.set_story_audio(story_id, str(out_path), engine.name)
        elapsed = round(time.time() - started, 1)
        log.info("故事 #%s 合成完成，耗时 %.1f 秒，引擎 %s", story_id, elapsed, engine.name)
        result = {
            "state": "done",
            "audio_url": f"/audio/story_{story_id}.wav",
            "engine": engine.name,
            "seconds": elapsed,
            "voice_id": voice["id"],
            "voice_name": voice["name"],
        }
    except Exception as e:  # 引擎内部异常，保留日志方便排查
        log.exception("故事 #%s 合成失败", story_id)
        result = {
            "state": "error",
            "error": str(e),
            "voice_id": voice["id"],
            "voice_name": voice["name"],
        }
    with _tts_jobs_lock:
        _tts_jobs[story_id] = result


@app.post("/api/stories/{story_id}/tts")
def api_synthesize(story_id: int, payload: dict):
    story = db.get_story(story_id)
    if not story:
        raise HTTPException(404, "故事不存在")

    # 优先用前端选的；没选就用故事创建时判断出的；再不行用默认声音
    voice_id = payload.get("voice_id") or story.get("voice_id")
    try:
        voice = db.get_voice(int(voice_id)) if voice_id not in (None, "") else None
    except (TypeError, ValueError):
        voice = None
    if not voice:
        voice = db.get_default_voice()
    if not voice:
        raise HTTPException(400, "还没有录过声音，请先回首页录一段")
    db.set_story_voice(story_id, voice["id"])

    try:
        engine = tts_engine.get_engine()
    except tts_engine.TTSError as e:
        raise HTTPException(400, str(e))

    with _tts_jobs_lock:
        job = _tts_jobs.get(story_id)
        if job and job.get("state") == "running":
            return job
        _tts_jobs[story_id] = {"state": "running"}

    threading.Thread(
        target=_run_tts_job,
        args=(story_id, voice, engine),
        daemon=True,
    ).start()
    return {"state": "running", "voice_id": voice["id"], "voice_name": voice["name"]}


@app.get("/api/stories/{story_id}/tts/status")
def api_tts_status(story_id: int):
    story = db.get_story(story_id)
    if not story:
        raise HTTPException(404, "故事不存在")
    with _tts_jobs_lock:
        job = _tts_jobs.get(story_id)
        if job:
            return dict(job)
    # 没有后台任务，但以前合成过，直接给出已有音频
    if story.get("audio_path"):
        return {
            "state": "done",
            "audio_url": f"/audio/story_{story_id}.wav",
            "engine": story.get("tts_engine"),
            "seconds": None,
            "voice_id": story.get("voice_id"),
        }
    return {"state": "idle"}


@app.get("/audio/{filename}")
def audio_file(filename: str):
    # 只允许访问音频目录里的文件，防止路径穿越
    path = (config.AUDIO_DIR / filename).resolve()
    if path.parent != config.AUDIO_DIR.resolve() or not path.exists():
        raise HTTPException(404, "音频不存在")
    return FileResponse(str(path), media_type="audio/wav")


@app.exception_handler(HTTPException)
def http_error(request: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


if __name__ == "__main__":
    import uvicorn

    ssl_cert = os.environ.get("BEDTIME_SSL_CERT")
    ssl_key = os.environ.get("BEDTIME_SSL_KEY")
    ssl_kwargs = {}
    if ssl_cert and ssl_key:
        ssl_kwargs = {"ssl_certfile": ssl_cert, "ssl_keyfile": ssl_key}
        log.info("已启用 HTTPS")

    uvicorn.run(app, host=config.HOST, port=config.PORT, **ssl_kwargs)