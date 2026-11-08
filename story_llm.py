"""调用云端大模型生成睡前故事。

使用的是 Anthropic Messages 兼容接口（你现有的第三方网关即可）。
不依赖任何 SDK，只用标准库，方便在 Linux / macOS 上运行。
"""

import json
import re
import urllib.error
import urllib.request

import config


class StoryError(Exception):
    pass


def _endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1/messages"):
        return base
    return base + "/v1/messages"


def _build_prompt(topic: str, age: int, voice_names=None, utterance=None) -> str:
    """拼提示词。

    有 utterance（孩子对着麦克风说的原话）时，让模型顺便：
    - 提炼出真正的故事主题（去掉“让奶奶讲”这类要求）
    - 判断孩子要求用哪个声音朗读
    """
    if utterance:
        names = "、".join(voice_names or [])
        names_line = (
            f"可用的声音只有：{names}。"
            if names
            else "目前还没有录过任何声音，voice 必须返回 null。"
        )
        intro = f"""孩子刚刚对着麦克风说：「{utterance}」

请先完成两件事：
1. 提炼故事主题：去掉“让奶奶讲”“用爸爸的声音”这类对朗读声音的要求，
   只保留孩子想听的故事内容；
2. 判断孩子有没有明确要求用某个声音来朗读。{names_line}
   - 只有明确要求时才返回那个声音名字，例如“让奶奶讲”“用爸爸的声音”“我要妈妈读”；
   - 如果名字只是故事内容的一部分，例如“小兔子的妈妈”，不要返回；
   - 判断不出来就返回 null。

然后按第 1 步提炼出的主题，为 {age} 岁孩子写一个睡前故事。
"""
        json_shape = (
            '{"topic": "提炼后的故事主题，不超过 30 字", '
            '"voice": "声音名字，没有要求就填 null", '
            '"title": "不超过 12 字的标题", '
            '"body": "正文，段落之间用 \\n\\n 分隔"}'
        )
    else:
        intro = f"""你是一位温柔的中文儿童睡前故事作家。请为 {age} 岁孩子写一个睡前故事。

主题：{topic}
"""
        json_shape = '{"title": "不超过 12 字的标题", "body": "正文，段落之间用 \\n\\n 分隔"}'

    return f"""{intro}
要求：
1. 全文 300~450 字，分 3~5 段，每段 2~4 句；
2. 语言舒缓、温暖，适合朗读，多用拟声词和轻微的重复节奏；
3. 不出现恐怖、暴力、争吵、危险等刺激情节；
4. 结尾轻柔，引导孩子安心入睡。

只输出如下 JSON，不要输出任何其他内容：
{json_shape}"""


def _clean_voice_name(raw) -> str:
    """把模型返回的声音名字收拾干净；null / “默认” 一律当成空。"""
    if isinstance(raw, dict):
        raw = raw.get("name") or raw.get("voice")
    name = str(raw or "").strip().strip("\"'“”‘’ ")
    if name.lower() in {"null", "none", "无", "默认", "default"}:
        return ""
    for suffix in ("的声音", "声音"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    return name


def _extract_json(text: str, want_meta: bool = False) -> dict:
    """模型偶尔会带 markdown 代码块或多余文字，尽量把 JSON 抠出来。"""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise StoryError("模型没有返回可解析的 JSON")
        data = json.loads(cleaned[start : end + 1])

    title = str(data.get("title") or "").strip()
    body = str(data.get("body") or "").strip()
    if not body:
        raise StoryError("模型返回的故事正文为空")
    result = {"title": title or "一个温柔的睡前故事", "body": body}
    if want_meta:
        result["topic"] = str(data.get("topic") or "").strip()
        result["voice_name"] = _clean_voice_name(data.get("voice"))
    return result


def generate_story(
    topic: str,
    age: int = 4,
    timeout: int = 120,
    voice_names=None,
    utterance=None,
) -> dict:
    topic = (topic or "").strip()
    utterance = (utterance or "").strip()
    if not topic and not utterance:
        raise StoryError("请先填写故事主题")

    if not config.ANTHROPIC_BASE_URL or not config.ANTHROPIC_API_KEY:
        raise StoryError(
            "还没有配置云端模型。请在项目根目录的 .env 里填写 "
            "ANTHROPIC_BASE_URL 和 ANTHROPIC_API_KEY。"
        )

    prompt = _build_prompt(topic, age, voice_names=voice_names, utterance=utterance or None)
    payload = {
        "model": config.ANTHROPIC_MODEL,
        "max_tokens": 1400,
        "temperature": 0.8,
        # 这个网关上的推理模型默认会先输出很长的 thinking，把 token 额度吃光。
        # 关掉思考后能直接输出 JSON；如果换的网关不认识这个参数，会自动重试。
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": prompt}],
    }

    def _post(body):
        req = urllib.request.Request(
            _endpoint(config.ANTHROPIC_BASE_URL),
            data=json.dumps(body).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-api-key": config.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        try:
            data = _post(payload)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code == 400 and "thinking" in detail.lower():
                payload.pop("thinking", None)
                data = _post(payload)
            else:
                raise StoryError(f"云端模型返回错误 {e.code}：{detail}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise StoryError(f"云端模型返回错误 {e.code}：{detail}")
    except urllib.error.URLError as e:
        raise StoryError(f"连不上云端模型：{e.reason}")
    except TimeoutError:
        raise StoryError("云端模型响应超时，请稍后重试")

    # 兼容返回里同时带 thinking 块的情况，只取 type == text 的内容
    blocks = data.get("content") or []
    text = "".join(
        b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
    )
    if not text:
        raise StoryError("云端模型没有返回文本内容")

    result = _extract_json(text, want_meta=bool(utterance))
    result["topic"] = result.get("topic") or topic or utterance
    result["voice_name"] = result.get("voice_name") or ""
    result["age"] = age
    return result