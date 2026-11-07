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
    try:
        age = int(payload.get("age") or 4)
    except (TypeError, ValueError):
        age = 4
    age = max(1, min(12, age))

    try:
        result = story_llm.generate_story(topic, age)
    except story_llm.StoryError as e:
        raise HTTPException(400, str(e))

    story_id = db.add_story(result["title"], result["body"], topic, age)
    log.info("生成故事 #%s 《%s》", story_id, result["title"])
    return db.get_story(story_id)


@app.get("/api/voices")
def api_list_voices():
    return db.list_voices()


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


@app.post("/api/stories/{story_id}/tts")
def api_synthesize(story_id: int, payload: dict):
    story = db.get_story(story_id)
    if not story:
        raise HTTPException(404, "故事不存在")

    voice_id = payload.get("voice_id")
    voice = db.get_voice(int(voice_id)) if voice_id else None
    if not voice:
        raise HTTPException(400, "请先录一段声音，或者选择一个已有的声音")

    try:
        engine = tts_engine.get_engine()
    except tts_engine.TTSError as e:
        raise HTTPException(400, str(e))

    out_path = config.AUDIO_DIR / f"story_{story_id}.wav"
    started = time.time()
    try:
        engine.synthesize(
            story["body"],
            voice["wav_path"],
            voice["ref_text"],
            out_path,
        )
    except tts_engine.TTSError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # 引擎内部异常，保留日志方便排查
        log.exception("合成失败")
        raise HTTPException(500, f"合成失败：{e}")

    db.set_story_audio(story_id, str(out_path), engine.name)
    log.info("故事 #%s 合成完成，耗时 %.1f 秒，引擎 %s", story_id, time.time() - started, engine.name)
    return {
        "audio_url": f"/audio/story_{story_id}.wav",
        "engine": engine.name,
        "seconds": round(time.time() - started, 1),
    }


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