#!/usr/bin/env python3
"""下载 ZipVoice 声音克隆模型（约 194 MB，支持断点续传）。

用法：
    python scripts/download_models.py

模型来自 ModelScope 上原项目的公开仓库，只下载一次，之后离线可用。
"""

import sys
import tarfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

BASE = "https://modelscope.cn/models/yuqingteck/mommy-story-on-device-models/resolve/master/zipvoice"

FILES = {
    "tokens.txt": 2570,
    "encoder.int8.onnx": 5570211,
    "decoder.int8.onnx": 124657100,
    "vocos_24khz.onnx": 54157409,
    "lexicon.txt": 1727147,
    "espeak-ng-data.tar.gz": 8978591,
}

TEST_FILES = {
    "test_wavs/leijun-1.wav": None,
    "test_wavs/prompt.txt": None,
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
                total = expected_size or 0
                last_report = time.time()
                with open(dest, mode) as f:
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                        have += len(chunk)
                        if total and time.time() - last_report > 1:
                            pct = have * 100 / total
                            print(f"\r    {pct:5.1f}%  {human(have)} / {human(total)}", end="", flush=True)
                            last_report = time.time()
                print()
            if expected_size and dest.stat().st_size != expected_size:
                raise IOError(f"大小不对：{dest.stat().st_size} != {expected_size}")
            return
        except Exception as e:
            print(f"  失败（第 {attempt} 次）：{e}")
            if attempt == retries:
                raise
            time.sleep(2)


def main():
    config.ensure_dirs()
    target = config.ZIPVOICE_DIR
    target.mkdir(parents=True, exist_ok=True)

    print(f"模型目录：{target}")
    print(f"需要下载约 {human(sum(FILES.values()))}")

    for name, size in FILES.items():
        download(f"{BASE}/{name}", target / name, size)

    print("解压 espeak-ng-data（旧版兼容用，可忽略）…")
    tar_path = target / "espeak-ng-data.tar.gz"
    out_dir = target / "espeak-ng-data"
    if not out_dir.exists():
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(target, filter="data")
        print("  解压完成")
    else:
        print("  已存在，跳过")

    print("下载示例声音（用于快速测试）…")
    for name in TEST_FILES:
        download(f"{BASE}/{name}", target / name)

    print("\n完成。文件清单：")
    for f in sorted(target.iterdir()):
        if f.is_file():
            print(f"  {human(f.stat().st_size):>10}  {f.name}")
        else:
            print(f"  {'<目录>':>10}  {f.name}/")

    print("\n下一步：")
    print("  python scripts/test_tts.py    # 用示例声音合成一句话，验证引擎")


if __name__ == "__main__":
    main()