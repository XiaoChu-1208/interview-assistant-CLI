"""Tiny YAML-driven i18n. Falls back: config → LANG env → English."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_LOCALES_DIR = Path(__file__).parent / "locales"
_cache: dict[str, dict] = {}
_current_lang = "en"


def available_languages() -> list[str]:
    return sorted(p.stem for p in _LOCALES_DIR.glob("*.yaml"))


def load(lang: str) -> dict:
    if lang in _cache:
        return _cache[lang]
    path = _LOCALES_DIR / f"{lang}.yaml"
    if not path.exists():
        path = _LOCALES_DIR / "en.yaml"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    _cache[lang] = data
    return data


def set_language(lang: str | None) -> None:
    """Pick a language. Order: explicit arg → env LANG → 'en'."""
    global _current_lang
    if not lang:
        env = os.environ.get("LANG", "")
        if env.lower().startswith("zh"):
            lang = "zh-CN"
        else:
            lang = "en"
    if lang not in available_languages():
        lang = "en"
    _current_lang = lang
    load(lang)


def current() -> str:
    return _current_lang


def t(key: str, **kwargs: Any) -> str:
    """Lookup `a.b.c` in the current locale, format with kwargs.

    Falls back to English if missing in the current locale, then to the key
    itself if missing everywhere.
    """
    for lang in (_current_lang, "en"):
        data = load(lang)
        node: Any = data
        ok = True
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                ok = False
                break
        if ok and isinstance(node, str):
            try:
                return node.format(**kwargs) if kwargs else node
            except (KeyError, IndexError):
                return node
    return key


# Initialize from env on import; cli/init may override later.
set_language(None)
