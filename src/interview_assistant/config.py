"""Config: TOML file at platformdirs path, with IA_* env overrides.

Schema (all sections optional; defaults filled in):

    [ui]      lang, theme
    [stt]     provider, groq_api_key, deepgram_api_key, model
    [chat]    base_url, api_key, model, fast_model,
              fallback_base_url, fallback_api_key, fallback_model,
              http_proxy
    [knowledge]   dirs
    [skills]      search_paths
    [hotkey]      ptt
    [stt_filter]  extra_hallucinations, extra_fillers
    [audio]       loopback_device, mic_device

Set IA_CHAT_API_KEY=... to override [chat].api_key, etc. (uppercase, dot→_).
"""
from __future__ import annotations

import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import platformdirs

if sys.version_info >= (3, 11):
    import tomllib  # type: ignore
else:
    import tomli as tomllib  # type: ignore

import tomli_w


APP_NAME = "interview-assistant"


DEFAULTS: dict[str, Any] = {
    "ui": {"lang": "", "theme": "auto"},
    "stt": {
        "provider": "groq",
        "groq_api_key": "",
        "deepgram_api_key": "",
        "model": "whisper-large-v3-turbo",
        "deepgram_model": "nova-3",
    },
    "chat": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key": "",
        "model": "llama-3.3-70b-versatile",
        "fast_model": "llama-3.1-8b-instant",
        "fallback_base_url": "",
        "fallback_api_key": "",
        "fallback_model": "",
        "http_proxy": "",
    },
    "knowledge": {"dirs": ["./knowledge"]},
    "skills": {
        "search_paths": [
            "./.cursor/skills",
            "~/.cursor/skills",
            "./.claude/skills",
            "~/.claude/skills",
        ]
    },
    "hotkey": {"ptt": "alt_r"},
    "stt_filter": {"extra_hallucinations": [], "extra_fillers": []},
    "audio": {"loopback_device": "", "mic_device": ""},
}


def config_dir() -> Path:
    """User config directory (cross-platform via platformdirs)."""
    return Path(platformdirs.user_config_dir(APP_NAME))


def config_path() -> Path:
    return config_dir() / "config.toml"


def state_dir() -> Path:
    p = Path(platformdirs.user_state_dir(APP_NAME))
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_dir() -> Path:
    p = Path(platformdirs.user_cache_dir(APP_NAME))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = deepcopy(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _apply_env(cfg: dict) -> dict:
    """IA_<SECTION>_<KEY>=value overrides."""
    for env_key, env_val in os.environ.items():
        if not env_key.startswith("IA_"):
            continue
        parts = env_key[3:].lower().split("_", 1)
        if len(parts) != 2:
            continue
        section, key = parts
        if section in cfg and key in cfg[section]:
            existing = cfg[section][key]
            if isinstance(existing, list):
                cfg[section][key] = [s.strip() for s in env_val.split(",") if s.strip()]
            elif isinstance(existing, bool):
                cfg[section][key] = env_val.lower() in ("1", "true", "yes", "on")
            elif isinstance(existing, int):
                try:
                    cfg[section][key] = int(env_val)
                except ValueError:
                    pass
            else:
                cfg[section][key] = env_val
    return cfg


def load() -> dict:
    """Load config: defaults ← file ← env."""
    cfg = deepcopy(DEFAULTS)
    p = config_path()
    if p.exists():
        with open(p, "rb") as f:
            disk = tomllib.load(f)
        cfg = _deep_merge(cfg, disk)
    cfg = _apply_env(cfg)
    return cfg


def save(cfg: dict) -> Path:
    """Persist config to disk."""
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    serializable = {k: v for k, v in cfg.items() if k in DEFAULTS}
    with open(p, "wb") as f:
        tomli_w.dump(serializable, f)
    return p


def expanduser_paths(paths: list[str]) -> list[Path]:
    return [Path(os.path.expanduser(p)).resolve() for p in paths]


def has_chat_creds(cfg: dict) -> bool:
    return bool(cfg.get("chat", {}).get("api_key"))


def has_stt_creds(cfg: dict) -> bool:
    stt = cfg.get("stt", {})
    if stt.get("provider") == "deepgram":
        return bool(stt.get("deepgram_api_key"))
    return bool(stt.get("groq_api_key"))
