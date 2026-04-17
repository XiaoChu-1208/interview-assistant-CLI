"""Cross-platform diagnostics + auto-fix.

`run(autofix=False)` produces a list of (status, message) and optionally tries
to repair what it can (Python-level via pip; OS-level via subprocess with the
user's consent).
"""
from __future__ import annotations

import importlib
import platform
import shutil
import subprocess
import sys
from typing import Callable

from . import audio_backend, config as _cfg, i18n, network, providers
from .theme import BGRN, BRED, BYEL, DIM, RST, B


CHECK = "✓"
CROSS = "✗"
WARN = "!"


def _emit(status: str, msg: str) -> tuple[str, str]:
    color = {CHECK: BGRN, CROSS: BRED, WARN: BYEL}.get(status, "")
    print(f"  {color}{status}{RST} {msg}")
    return status, msg


def _fix_brew_blackhole() -> bool:
    if not shutil.which("brew"):
        return False
    try:
        subprocess.run(["brew", "install", "blackhole-2ch"], check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _fix_apt_portaudio() -> bool:
    if not shutil.which("apt"):
        return False
    try:
        subprocess.run(["sudo", "apt", "install", "-y", "portaudio19-dev", "libportaudio2"], check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _open_macos_accessibility() -> bool:
    try:
        subprocess.Popen(
            ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"]
        )
        return True
    except Exception:
        return False


def _check_python() -> tuple[str, str]:
    ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        return _emit(CHECK, i18n.t("doctor.python_ok", ver=ver))
    return _emit(CROSS, i18n.t("doctor.python_old", ver=ver))


def _check_pkg(modname: str, pip_name: str | None = None) -> tuple[str, str]:
    pip_name = pip_name or modname
    try:
        importlib.import_module(modname)
        return _emit(CHECK, i18n.t("doctor.pkg_ok", name=modname))
    except ImportError:
        return _emit(WARN, i18n.t("doctor.pkg_missing", name=modname, pkg=pip_name))


def _check_audio() -> list[tuple[str, str]]:
    out = []
    lb = audio_backend.find_loopback()
    if lb.id is not None:
        out.append(_emit(CHECK, i18n.t("doctor.audio_loopback_ok", name=lb.name)))
    else:
        out.append(_emit(WARN, i18n.t("doctor.audio_loopback_none")))
        sysname = audio_backend.system()
        if sysname == "Darwin":
            out.append(_emit(WARN, i18n.t("doctor.fix_brew_blackhole")))
        elif sysname == "Linux":
            out.append(_emit(WARN, i18n.t("doctor.fix_apt_portaudio")))

    mic = audio_backend.find_microphone()
    if mic.id is not None:
        out.append(_emit(CHECK, i18n.t("doctor.audio_mic_ok", name=mic.name)))
    else:
        out.append(_emit(WARN, i18n.t("doctor.audio_mic_none")))
    return out


def _check_config(cfg: dict) -> tuple[str, str]:
    p = _cfg.config_path()
    if p.exists():
        return _emit(CHECK, i18n.t("doctor.config_ok", path=str(p)))
    return _emit(WARN, i18n.t("doctor.config_missing"))


def _check_chat_api(cfg: dict) -> tuple[str, str] | None:
    chat = cfg.get("chat", {})
    if not chat.get("api_key"):
        return None
    ok, err = providers.ping(chat["base_url"], chat["api_key"], chat.get("fast_model") or chat["model"], chat.get("http_proxy", ""))
    if ok:
        return _emit(CHECK, i18n.t("doctor.api_ok", provider=chat["base_url"]))
    return _emit(WARN, i18n.t("doctor.api_fail", provider=chat["base_url"], err=err[:120]))


def _check_network(cfg: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    proxy = cfg.get("chat", {}).get("http_proxy", "")
    inet = network.probe(network.PROBE_URLS["internet"], proxy=proxy)
    if inet.ok:
        out.append(_emit(CHECK, f"internet reachable ({inet.elapsed_ms}ms)"))
    else:
        out.append(_emit(WARN, f"internet unreachable: {inet.error[:80]}"))
    base = cfg.get("chat", {}).get("base_url", "")
    if base:
        target = "groq" if "groq" in base else "openai" if "openai" in base else "internet"
        tgt = network.probe(network.PROBE_URLS[target], proxy=proxy)
        if tgt.ok:
            out.append(_emit(CHECK, f"{target} reachable ({tgt.elapsed_ms}ms)"))
        else:
            out.append(_emit(WARN, f"{target} unreachable: {tgt.error[:80]}"))
    sysp = network.detect_system_proxy()
    if sysp:
        out.append(_emit(CHECK, f"system proxy detected: {sysp}"))
    elif proxy:
        out.append(_emit(CHECK, f"configured proxy: {proxy}"))
    return out


def run(cfg: dict | None = None, *, autofix: bool = False) -> list[tuple[str, str]]:
    """Run all checks. Returns the (status, message) tuples emitted."""
    if cfg is None:
        cfg = _cfg.load()

    print(f"\n  {B}{i18n.t('doctor.title')}{RST}\n")

    out: list[tuple[str, str]] = []
    out.append(_check_python())
    print(f"\n  {DIM}— python packages —{RST}")
    out.append(_check_pkg("numpy"))
    out.append(_check_pkg("sounddevice"))
    out.append(_check_pkg("httpx"))
    out.append(_check_pkg("yaml", "PyYAML"))
    out.append(_check_pkg("fastembed", "interview-assistant[embed]"))
    out.append(_check_pkg("pynput", "interview-assistant[hotkey]"))

    sysname = audio_backend.system()
    if sysname == "Windows":
        out.append(_check_pkg("soundcard", "interview-assistant[windows]"))
        out.append(_check_pkg("colorama", "interview-assistant[windows]"))

    print(f"\n  {DIM}— audio devices —{RST}")
    out.extend(_check_audio())

    print(f"\n  {DIM}— config —{RST}")
    out.append(_check_config(cfg))

    print(f"\n  {DIM}— network —{RST}")
    out.extend(_check_network(cfg))

    api = _check_chat_api(cfg)
    if api:
        out.append(api)

    if autofix:
        print(f"\n  {B}auto-fix{RST}\n")
        for status, msg in out:
            if status != CROSS and status != WARN:
                continue
            if "blackhole" in msg.lower() and sysname == "Darwin":
                print(f"  {DIM}{i18n.t('doctor.autofix_run', cmd='brew install blackhole-2ch')}{RST}")
                ok = _fix_brew_blackhole()
                _emit(CHECK if ok else CROSS,
                      i18n.t("doctor.autofix_done") if ok else i18n.t("doctor.autofix_failed", err="brew not found"))
            elif "portaudio" in msg.lower() and sysname == "Linux":
                print(f"  {DIM}{i18n.t('doctor.autofix_run', cmd='sudo apt install portaudio19-dev')}{RST}")
                ok = _fix_apt_portaudio()
                _emit(CHECK if ok else CROSS,
                      i18n.t("doctor.autofix_done") if ok else i18n.t("doctor.autofix_failed", err="apt not found"))
    print()
    return out


def open_macos_accessibility() -> bool:
    return _open_macos_accessibility()
