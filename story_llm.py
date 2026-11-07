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


def _build_prompt(topic: str, age: int) -> str:
    return f"""你是一位温柔的中文儿童睡前故事作家。请为 {age} 岁孩子写一个睡前故事。

主题：{topic}

要求：
1. 全文 300~450 字，分 3~5 段，每段 2~4 句；
2. 语言舒缓、温暖，适合朗读，多用拟声词和轻微的重复节奏；
3. 不出现恐怖、暴力、争吵、危险等刺激情节；
4. 结尾轻柔，引导孩子安心入睡。

只输出如下 JSON，不要输出任何其他内容：
{{"title": "不超过 12 字的标题", "body": "正文，段落之间用 \\n\\n 分隔"}}"""


def _extract_json(text: str) -> dict:
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
    return {"title": title or "一个温柔的睡前故事", "body": body}


def generate_story(topic: str, age: int = 4, timeout: int = 120) -> dict:
    topic = (topic or "").strip()
    if not topic:
        raise StoryError("请先填写故事主题")

    if not config.ANTHROPIC_BASE_URL or not config.ANTHROPIC_API_KEY:
        raise StoryError(
            "还没有配置云端模型。请在项目根目录的 .env 里填写 "
            "ANTHROPIC_BASE_URL 和 ANTHROPIC_API_KEY。"
        )

    payload = {
        "model": config.ANTHROPIC_MODEL,
        "max_tokens": 1400,
        "temperature": 0.8,
        # 这个网关上的推理模型默认会先输出很长的 thinking，把 token 额度吃光。
        # 关掉思考后能直接输出 JSON；如果换的网关不认识这个参数，会自动重试。
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": _build_prompt(topic, age)}],
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

    result = _extract_json(text)
    result["topic"] = topic
    result["age"] = age
    return result