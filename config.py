"""项目配置：路径、云端模型接口、TTS 引擎选择。

所有敏感配置都从环境变量或项目根目录的 .env 读取，
.env 不要提交到 git，也不要发给别人。
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ---- 数据目录 ----
DATA_DIR = ROOT / "data"
AUDIO_DIR = DATA_DIR / "audio"
VOICE_DIR = DATA_DIR / "voices"
DB_PATH = DATA_DIR / "stories.db"

# ---- 模型目录 ----
MODEL_DIR = Path(os.environ.get("BEDTIME_MODEL_DIR", str(ROOT / "models")))
ZIPVOICE_DIR = MODEL_DIR / "zipvoice"
# 本地语音识别模型（把小朋友说的话转成文字）
ASR_DIR = Path(
    os.environ.get("BEDTIME_ASR_DIR", str(MODEL_DIR / "asr" / "paraformer-zh-small"))
)

# ---- 云端故事模型（Anthropic 兼容接口）----
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4.1-flash-1017")

# ---- TTS 引擎 ----
# auto  : 能用 sherpa-onnx 且模型齐全就用它，否则在 macOS 上退回系统语音
# sherpa: 强制使用 ZipVoice 声音克隆
# say   : 强制使用 macOS 系统语音（仅用于调试界面）
TTS_ENGINE = os.environ.get("BEDTIME_TTS_ENGINE", "auto")
TTS_THREADS = int(os.environ.get("BEDTIME_TTS_THREADS", "2"))
TTS_NUM_STEPS = int(os.environ.get("BEDTIME_TTS_NUM_STEPS", "4"))

# ---- 语音识别 ----
ASR_THREADS = int(os.environ.get("BEDTIME_ASR_THREADS", "2"))

HOST = os.environ.get("BEDTIME_HOST", "0.0.0.0")
PORT = int(os.environ.get("BEDTIME_PORT", "8000"))


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """读取简单的 KEY=VALUE 文件，不覆盖已有的环境变量。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if value[:1] == value[-1:] and value[:1] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def refresh() -> None:
    """load_dotenv 之后重新读取配置。"""
    global ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY, ANTHROPIC_MODEL
    global TTS_ENGINE, TTS_THREADS, TTS_NUM_STEPS
    ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4.1-flash-1017")
    TTS_ENGINE = os.environ.get("BEDTIME_TTS_ENGINE", "auto")
    TTS_THREADS = int(os.environ.get("BEDTIME_TTS_THREADS", "2"))
    TTS_NUM_STEPS = int(os.environ.get("BEDTIME_TTS_NUM_STEPS", "4"))
    global ASR_THREADS
    ASR_THREADS = int(os.environ.get("BEDTIME_ASR_THREADS", "2"))


def ensure_dirs() -> None:
    for d in (DATA_DIR, AUDIO_DIR, VOICE_DIR, MODEL_DIR, DATA_DIR / "tmp"):
        d.mkdir(parents=True, exist_ok=True)