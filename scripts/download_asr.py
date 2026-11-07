#!/usr/bin/env python3
"""下载本地语音识别模型（Paraformer 中文小模型，约 78 MB）。

用法：
    python scripts/download_asr.py

模型来自 sherpa-onnx 的公开仓库（HuggingFace 镜像 hf-mirror.com），
只下载一次，之后离线可用，孩子的声音不会上传到任何服务器。
"""

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

BASE = (
    "https://hf-mirror.com/csukuangfj/"
    "sherpa-onnx-paraformer-zh-small-2024-03-09/resolve/main"
)

FILES = {
    "model.int8.onnx": 81828675,
    "tokens.txt": 75352,
}


def human(n):
    return f"{n / 1024 / 1024:.1f} MB"


def download(url, dest: Path, expected_size=None, retries=3):
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, retries + 1):
        have = dest.stat().st_size if dest.exists() else 0
        if expected_size and have >= expected_size:
            print(f"  已存在，跳过：{dest.name}")
            return
        headers = {"User-Agent": "bedtime-story/1.0"}
        if have:
            headers["Range"] = f"bytes={have}-"
            print(f"  续传 {dest.name}，已有 {human(have)}")
        else:
            print(f"  下载 {dest.name} …")

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                mode = "ab" if have and resp.status == 206 else "wb"
                if mode == "wb":
                    have = 0
                with open(dest, mode) as f:
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                        have += len(chunk)
                        if expected_size:
                            print(
                                f"\r      {have / expected_size * 100:5.1f}%"
                                f"  {human(have)} / {human(expected_size)}",
                                end="",
                                flush=True,
                            )
            print()
            if expected_size and dest.stat().st_size != expected_size:
                print(f"  大小不符（{dest.stat().st_size}），重试 {attempt}/{retries}")
                continue
            return
        except Exception as e:  # 网络中断很常见，续传即可
            print(f"\n  第 {attempt} 次失败：{e}")
            if attempt == retries:
                raise


def main():
    target = Path(config.ASR_DIR)
    total = sum(FILES.values())
    print(f"识别模型目录：{target}")
    print(f"需要下载约 {human(total)}")
    for name, size in FILES.items():
        download(f"{BASE}/{name}?download=true", target / name, size)
    print("完成。启动服务后就能用语音说出故事主题了。")


if __name__ == "__main__":
    main()