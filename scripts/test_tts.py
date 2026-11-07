#!/usr/bin/env python3
"""用示例声音合成一句话，验证 TTS 引擎是否正常。

用法：
    python scripts/test_tts.py

输出：data/audio/test.wav
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402
import tts_engine  # noqa: E402

TEXT = "宝宝，今天妈妈给你讲一个小兔子的故事。月亮升起来了，小兔子也要睡觉啦。"


def main():
    config.load_dotenv()
    config.refresh()
    config.ensure_dirs()

    engine = tts_engine.get_engine()
    print(f"使用引擎：{engine.name}")

    ref_wav = config.ZIPVOICE_DIR / "test_wavs" / "leijun-1.wav"
    prompt_file = config.ZIPVOICE_DIR / "test_wavs" / "prompt.txt"
    ref_text = prompt_file.read_text(encoding="utf-8").strip() if prompt_file.exists() else ""

    if engine.name == "sherpa":
        if not ref_wav.exists():
            print(f"缺少示例音频：{ref_wav}")
            print("请先运行 python scripts/download_models.py")
            return 1
        print(f"参考音频：{ref_wav.name}")
        print(f"参考文字：{ref_text[:40]}…")

    out = config.AUDIO_DIR / "test.wav"
    started = time.time()

    def progress(done, total):
        print(f"  合成进度 {done}/{total} 句")

    engine.synthesize(TEXT, ref_wav, ref_text, out, on_progress=progress)
    print(f"\n完成：{out}")
    print(f"耗时：{time.time() - started:.1f} 秒")
    print("可以播放听听效果。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())