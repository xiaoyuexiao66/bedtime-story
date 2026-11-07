"""本地语音识别：把小朋友说的话转成文字。

用 sherpa-onnx 的 Paraformer 中文模型（约 78MB），完全在本机运行，
孩子的声音不会上传到任何服务器。
"""

import re
import threading
from pathlib import Path

import config


class ASRError(Exception):
    pass


class ParaformerASR:
    """基于 Paraformer 的离线中文识别。"""

    name = "paraformer"

    def __init__(self):
        self._rec = None
        self._lock = threading.Lock()

    def available(self) -> bool:
        try:
            import sherpa_onnx  # noqa: F401
        except Exception:
            return False
        d = config.ASR_DIR
        return (d / "model.int8.onnx").exists() and (d / "tokens.txt").exists()

    def _load(self):
        if self._rec is not None:
            return self._rec
        import sherpa_onnx

        d = config.ASR_DIR
        self._rec = sherpa_onnx.OfflineRecognizer.from_paraformer(
            paraformer=str(d / "model.int8.onnx"),
            tokens=str(d / "tokens.txt"),
            num_threads=config.ASR_THREADS,
            sample_rate=16000,
            feature_dim=80,
            decoding_method="greedy_search",
        )
        return self._rec

    def warm_up(self):
        """提前把模型加载进内存，孩子第一次点按钮时就不用干等。"""
        with self._lock:
            self._load()

    def transcribe(self, wav_path) -> str:
        import numpy as np
        import soundfile as sf

        path = Path(wav_path)
        if not path.exists():
            raise ASRError("找不到要识别的录音")

        samples, sr = sf.read(str(path), dtype="float32", always_2d=False)
        if getattr(samples, "ndim", 1) > 1:
            samples = samples.mean(axis=1)
        samples = np.ascontiguousarray(samples, dtype=np.float32)
        if samples.size == 0:
            raise ASRError("录音是空的")

        # sherpa 的 recognizer 不是线程安全的，加载和识别都串行
        with self._lock:
            rec = self._load()
            stream = rec.create_stream()
            stream.accept_waveform(int(sr), samples)
            rec.decode_stream(stream)
            text = stream.result.text or ""
        return _clean(text)


def _clean(text: str) -> str:
    """去掉多余空白和首尾标点，方便直接当故事主题。"""
    text = re.sub(r"\s+", "", text.strip())
    return text.strip("，。！？、,.!?；;：:")


_instance = None
_instance_lock = threading.Lock()


def get_asr() -> ParaformerASR:
    """整个进程只创建一个识别引擎，避免每次请求都重新加载 78MB 模型。"""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                engine = ParaformerASR()
                if not engine.available():
                    raise ASRError(
                        "语音识别模型还没准备好，请先运行 python scripts/download_asr.py"
                    )
                _instance = engine
    return _instance