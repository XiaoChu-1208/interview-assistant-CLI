"""Speech-to-text providers: Groq Whisper, Deepgram (streaming), local faster-whisper.

`transcribe_audio(np_audio, cfg, sample_rate=16000) -> str` is the workhorse.
For streaming Deepgram, see `audio.DeepgramListener`.
"""
from __future__ import annotations

import io
import wave

import httpx
import numpy as np


def _to_wav_bytes(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767).astype(np.int16).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def transcribe_audio(audio: np.ndarray, cfg: dict, sample_rate: int = 16000) -> str:
    """Transcribe a numpy audio buffer. Returns text (or '' on failure)."""
    stt = cfg.get("stt", {})
    provider = stt.get("provider", "groq")
    proxy = cfg.get("chat", {}).get("http_proxy", "")

    if provider == "local":
        return _transcribe_local(audio, sample_rate, stt.get("model", "small"))
    if provider == "deepgram":
        return _transcribe_deepgram(audio, stt, proxy, sample_rate)
    return _transcribe_groq(audio, stt, proxy, sample_rate)


def _transcribe_groq(audio, stt, proxy, sample_rate) -> str:
    api_key = stt.get("groq_api_key", "")
    model = stt.get("model", "whisper-large-v3-turbo")
    if not api_key:
        return ""
    wav = _to_wav_bytes(audio, sample_rate)
    files = {
        "file": ("audio.wav", wav, "audio/wav"),
        "model": (None, model),
        "response_format": (None, "json"),
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    kw = {"timeout": 30.0}
    if proxy:
        kw["proxy"] = proxy
    try:
        with httpx.Client(**kw) as c:
            r = c.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers=headers, files=files,
            )
        if r.status_code == 200:
            return (r.json().get("text") or "").strip()
        return ""
    except Exception:
        return ""


def _transcribe_deepgram(audio, stt, proxy, sample_rate) -> str:
    api_key = stt.get("deepgram_api_key", "")
    model = stt.get("deepgram_model", "nova-3")
    if not api_key:
        return ""
    wav = _to_wav_bytes(audio, sample_rate)
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "audio/wav",
    }
    kw = {"timeout": 30.0}
    if proxy:
        kw["proxy"] = proxy
    try:
        with httpx.Client(**kw) as c:
            r = c.post(
                f"https://api.deepgram.com/v1/listen?model={model}&smart_format=true&language=zh",
                headers=headers, content=wav,
            )
        if r.status_code != 200:
            return ""
        data = r.json()
        return data["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
    except Exception:
        return ""


_LOCAL_MODEL = None


def _transcribe_local(audio, sample_rate, model_size="small") -> str:
    """faster-whisper local fallback. Lazy-loaded."""
    global _LOCAL_MODEL
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return ""
    if _LOCAL_MODEL is None:
        _LOCAL_MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = _LOCAL_MODEL.transcribe(audio, language=None, beam_size=1)
    return " ".join(s.text for s in segments).strip()
