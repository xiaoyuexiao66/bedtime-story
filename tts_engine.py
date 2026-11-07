"""语音合成（TTS）引擎。

两种实现：
- SherpaZipVoiceEngine：ZipVoice 声音克隆，真正用你的声音朗读（Linux 上使用）
- SayEngine：macOS 自带语音，只用于在 Mac 上调试界面（没有克隆能力）

上层只关心：synthesize(文本, 参考音频, 参考音频对应文字, 输出路径)。
"""

import re
import shutil
import subprocess
from pathlib import Path

import config

try:  # numpy 一定会有，但保持友好的报错
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


class TTSError(Exception):
    pass


def split_sentences(text: str, max_len: int = 60) -> list:
    """把故事切成一两句一段，便于边合成边播放，也让长句更稳定。"""
    parts = re.split(r"(?<=[。！？!?；;])|\n+", text)
    sentences = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 过长的句子继续按逗号/顿号切开
        while len(part) > max_len:
            cut = max(
                part.rfind("，", 0, max_len),
                part.rfind(",", 0, max_len),
                part.rfind("、", 0, max_len),
            )
            if cut <= 0:
                cut = max_len
            sentences.append(part[: cut + 1].strip())
            part = part[cut + 1 :].strip()
        if part:
            sentences.append(part)
    return sentences


class SherpaZipVoiceEngine:
    """基于 sherpa-onnx 的 ZipVoice 零样本声音克隆。"""

    name = "sherpa"

    def __init__(self):
        self._tts = None

    def available(self) -> bool:
        try:
            import sherpa_onnx  # noqa: F401
        except Exception:
            return False
        required = [
            "tokens.txt",
            "encoder.int8.onnx",
            "decoder.int8.onnx",
            "vocos_24khz.onnx",
            "lexicon.txt",
        ]
        return all((config.ZIPVOICE_DIR / f).exists() for f in required)

    def _load(self):
        if self._tts is not None:
            return self._tts
        import sherpa_onnx

        d = config.ZIPVOICE_DIR
        cfg = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                zipvoice=sherpa_onnx.OfflineTtsZipvoiceModelConfig(
                    tokens=str(d / "tokens.txt"),
                    encoder=str(d / "encoder.int8.onnx"),
                    decoder=str(d / "decoder.int8.onnx"),
                    vocoder=str(d / "vocos_24khz.onnx"),
                    lexicon=str(d / "lexicon.txt"),
                ),
                num_threads=config.TTS_THREADS,
                provider="cpu",
            )
        )
        self._tts = sherpa_onnx.OfflineTts(cfg)
        return self._tts

    def synthesize(self, text, ref_wav, ref_text, out_path, on_progress=None):
        import soundfile as sf

        if np is None:
            raise TTSError("缺少 numpy，请先安装依赖")

        wav_path = Path(ref_wav)
        if not wav_path.exists():
            raise TTSError("找不到参考音频，请先录一段声音")
        if not (ref_text or "").strip():
            raise TTSError("请填写参考音频里说的文字")

        samples, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
        if getattr(samples, "ndim", 1) > 1:
            samples = samples.mean(axis=1)
        samples = np.ascontiguousarray(samples, dtype=np.float32)
        if samples.size == 0:
            raise TTSError("参考音频是空的")

        tts = self._load()
        sentences = split_sentences(text)
        if not sentences:
            raise TTSError("故事正文是空的")

        pieces = []
        out_sr = 24000
        for i, sentence in enumerate(sentences):
            audio = tts.generate(
                sentence,
                ref_text.strip(),
                samples,
                int(sr),
                speed=1.0,
                num_steps=config.TTS_NUM_STEPS,
            )
            arr = np.asarray(audio.samples, dtype=np.float32)
            out_sr = int(audio.sample_rate)
            pieces.append(arr)
            # 句间留一点停顿，听起来更自然
            if i < len(sentences) - 1:
                pieces.append(np.zeros(int(out_sr * 0.18), dtype=np.float32))
            if on_progress:
                on_progress(i + 1, len(sentences))

        full = np.concatenate(pieces) if pieces else np.zeros(1, dtype=np.float32)
        sf.write(str(out_path), full, out_sr, subtype="PCM_16")
        return out_path


class SayEngine:
    """macOS 系统语音。只在开发调试时用，不能克隆声音。"""

    name = "say"

    def available(self) -> bool:
        return bool(shutil.which("say") and shutil.which("afconvert"))

    def synthesize(self, text, ref_wav=None, ref_text=None, out_path=None, on_progress=None):
        out_path = Path(out_path)
        tmp_aiff = out_path.with_suffix(".aiff")
        # Tingting 是 macOS 常见的中文语音；没有就用默认语音
        voice = "Tingting"
        result = subprocess.run(
            ["say", "-v", voice, "-o", str(tmp_aiff), text],
            cwd=str(out_path.parent),
            capture_output=True,
        )
        if result.returncode != 0:
            subprocess.run(
                ["say", "-o", str(tmp_aiff), text],
                cwd=str(out_path.parent),
                check=True,
            )
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@24000", str(tmp_aiff), str(out_path)],
            check=True,
        )
        tmp_aiff.unlink(missing_ok=True)
        if on_progress:
            on_progress(1, 1)
        return out_path


def get_engine():
    if config.TTS_ENGINE == "sherpa":
        engine = SherpaZipVoiceEngine()
        if not engine.available():
            raise TTSError(
                "ZipVoice 模型还没准备好。请先运行 python scripts/download_models.py，"
                "并确认已安装 sherpa-onnx。"
            )
        return engine
    if config.TTS_ENGINE == "say":
        engine = SayEngine()
        if not engine.available():
            raise TTSError("当前系统没有 say 命令，请改用 sherpa 引擎")
        return engine

    # auto：优先真实的克隆引擎，失败才退回系统语音
    engine = SherpaZipVoiceEngine()
    if engine.available():
        return engine
    say = SayEngine()
    if say.available():
        return say
    raise TTSError(
        "没有可用的 TTS 引擎：既没有 ZipVoice 模型，也没有 macOS 的 say 命令。"
    )