"""Audio capture: continuous listener (interviewer) and PTT recorder (you).

`AudioListener` does VAD-style chunking on a system-audio loopback, transcribes
each chunk via STT, and dispatches the cleaned text. `PushToTalkRecorder`
records while a hotkey is held and dispatches once on release.
"""
from __future__ import annotations

import threading
import time

import numpy as np
import sounddevice as sd

from .stt import transcribe_audio
from .stt_filter import STTFilter
from .theme import BGRN, BRED, DIM, RST, WARM, B
from . import i18n


SAMPLE_RATE = 48000
WHISPER_RATE = 16000
SILENCE_THRESHOLD = 0.005
SILENCE_DURATION = 1.2
MIN_AUDIO_DURATION = 0.8


def _resample(audio: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return audio
    n_dst = int(len(audio) * dst / src)
    return np.interp(
        np.linspace(0, len(audio), n_dst, endpoint=False),
        np.arange(len(audio)),
        audio,
    ).astype(np.float32)


class AudioListener:
    """Continuous VAD-chunked listener for the interviewer side."""

    def __init__(self, device_id: int, on_transcript, cfg: dict, stt_filter: STTFilter):
        self.device_id = device_id
        self.on_transcript = on_transcript
        self.cfg = cfg
        self.filter = stt_filter
        self.running = False
        self.buffer: list[np.ndarray] = []
        self.silence_counter = 0.0
        self.is_speaking = False
        self.stream = None

    def _callback(self, indata, frames, time_info, status):
        audio = np.mean(indata, axis=1) if indata.shape[1] > 1 else indata[:, 0].copy()
        rms = float(np.sqrt(np.mean(audio ** 2)))

        if rms > SILENCE_THRESHOLD:
            self.buffer.append(audio)
            self.silence_counter = 0
            if not self.is_speaking:
                self.is_speaking = True
                print(f"\r{DIM}  {i18n.t('run.listening')}{RST}", end="", flush=True)
        elif self.is_speaking:
            self.silence_counter += frames / SAMPLE_RATE
            self.buffer.append(audio)
            if self.silence_counter >= SILENCE_DURATION:
                self.is_speaking = False
                self.silence_counter = 0
                full = np.concatenate(self.buffer)
                self.buffer = []
                dur = len(full) / SAMPLE_RATE
                if dur >= MIN_AUDIO_DURATION:
                    print(f"\r{DIM}  {i18n.t('run.transcribing', dur=f'{dur:.1f}')}{RST}    ",
                          end="", flush=True)
                    threading.Thread(target=self._process, args=(full,), daemon=True).start()

    def _process(self, audio: np.ndarray):
        audio_16k = _resample(audio, SAMPLE_RATE, WHISPER_RATE)
        text = transcribe_audio(audio_16k, self.cfg, WHISPER_RATE)
        if not text or len(text) <= 1:
            print(f"\r{DIM}  {i18n.t('run.empty_transcription')}{RST}      ", flush=True)
            return
        cleaned = text.strip()
        if self.filter.is_hallucination(cleaned):
            print(f"\r{DIM}  {i18n.t('run.hallucination_filtered')}{RST}      ", flush=True)
            return
        if self.filter.is_filler(cleaned):
            print(f"\r{DIM}  {i18n.t('run.filler_skipped')}{RST}      ", flush=True)
            return
        self.on_transcript(cleaned, source="interviewer")

    def start(self):
        self.running = True
        ch = min(sd.query_devices(self.device_id)["max_input_channels"], 2)
        self.stream = sd.InputStream(
            device=self.device_id, channels=ch, samplerate=SAMPLE_RATE,
            callback=self._callback, blocksize=4800,
        )
        self.stream.start()

    def stop(self):
        self.running = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass


class PushToTalkRecorder:
    """Records while held; transcribes + dispatches on release."""

    def __init__(self, device_id: int, on_transcript, cfg: dict, stt_filter: STTFilter):
        self.device_id = device_id
        self.on_transcript = on_transcript
        self.cfg = cfg
        self.filter = stt_filter
        self.recording = False
        self.buffer: list[np.ndarray] = []
        self.stream = None

    def _callback(self, indata, frames, time_info, status):
        if not self.recording:
            return
        audio = np.mean(indata, axis=1) if indata.shape[1] > 1 else indata[:, 0].copy()
        self.buffer.append(audio)

    def start(self):
        if self.recording:
            return
        self.buffer = []
        self.recording = True
        try:
            ch = min(sd.query_devices(self.device_id)["max_input_channels"], 2)
            self.stream = sd.InputStream(
                device=self.device_id, channels=ch, samplerate=SAMPLE_RATE,
                callback=self._callback, blocksize=4800,
            )
            self.stream.start()
            print(f"\r  {BGRN}● {i18n.t('run.ptt_recording')}{RST}", end="", flush=True)
        except Exception as e:
            self.recording = False
            print(f"\n{BRED}  ptt failed: {e}{RST}\n", flush=True)

    def stop(self):
        if not self.recording:
            return
        self.recording = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        if not self.buffer:
            return
        full = np.concatenate(self.buffer)
        self.buffer = []
        dur = len(full) / SAMPLE_RATE
        if dur < 0.4:
            print(f"\r  {DIM}{i18n.t('run.ptt_too_short', dur=f'{dur:.1f}')}{RST}", flush=True)
            return
        threading.Thread(target=self._process, args=(full,), daemon=True).start()

    def _process(self, audio: np.ndarray):
        audio_16k = _resample(audio, SAMPLE_RATE, WHISPER_RATE)
        text = transcribe_audio(audio_16k, self.cfg, WHISPER_RATE)
        if not text or len(text) <= 1:
            return
        cleaned = text.strip()
        if self.filter.is_hallucination(cleaned):
            return
        self.on_transcript(cleaned, source="you")
