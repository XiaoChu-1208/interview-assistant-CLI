"""Cross-platform audio device discovery.

* macOS:   loopback = BlackHole / Loopback / Soundflower / VB-Cable
* Windows: loopback = WASAPI loopback (requires `soundcard` or `pyaudiowpatch`)
* Linux:   loopback = any PulseAudio `*.monitor` device

Microphone discovery prefers the system default input, skipping virtuals.
"""
from __future__ import annotations

import platform
from dataclasses import dataclass

import sounddevice as sd


_VIRTUAL_NAMES = ("blackhole", "loopback", "soundflower", "vb-cable", "aggregate", ".monitor", "monitor of")


@dataclass
class Device:
    id: int | None
    name: str
    channels: int = 0


def system() -> str:
    return platform.system()  # 'Darwin' | 'Windows' | 'Linux'


def find_loopback() -> Device:
    """Return the best system-audio capture device available."""
    sysname = system()
    devices = list(enumerate(sd.query_devices()))

    if sysname == "Darwin":
        for i, d in devices:
            if "blackhole" in d["name"].lower() and d["max_input_channels"] > 0:
                return Device(i, d["name"], d["max_input_channels"])
        for i, d in devices:
            n = d["name"].lower()
            if any(v in n for v in ("loopback", "soundflower", "vb-cable")) and d["max_input_channels"] > 0:
                return Device(i, d["name"], d["max_input_channels"])
        return Device(None, "")

    if sysname == "Windows":
        for i, d in devices:
            if "loopback" in d["name"].lower() and d["max_input_channels"] > 0:
                return Device(i, d["name"], d["max_input_channels"])
        for i, d in devices:
            n = d["name"].lower()
            if "stereo mix" in n and d["max_input_channels"] > 0:
                return Device(i, d["name"], d["max_input_channels"])
        return Device(None, "")

    for i, d in devices:
        n = d["name"].lower()
        if (".monitor" in n or "monitor of" in n) and d["max_input_channels"] > 0:
            return Device(i, d["name"], d["max_input_channels"])
    return Device(None, "")


def find_microphone() -> Device:
    """Return the user's mic — prefer default input, skip virtuals."""
    try:
        default_in = sd.default.device[0]
        if isinstance(default_in, int) and default_in >= 0:
            d = sd.query_devices(default_in)
            n = d.get("name", "").lower()
            if d.get("max_input_channels", 0) > 0 and not any(v in n for v in _VIRTUAL_NAMES):
                return Device(default_in, d["name"], d["max_input_channels"])
    except Exception:
        pass
    for i, d in enumerate(sd.query_devices()):
        n = d.get("name", "").lower()
        if d.get("max_input_channels", 0) > 0 and not any(v in n for v in _VIRTUAL_NAMES):
            return Device(i, d["name"], d["max_input_channels"])
    return Device(None, "")


def list_input_devices() -> list[Device]:
    return [
        Device(i, d["name"], d["max_input_channels"])
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]
