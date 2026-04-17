"""Skill discovery + runtime hooks.

A "skill" is a directory containing `SKILL.md` (with YAML frontmatter) and
optional `data/` files. The frontmatter may include a `runtime` block:

    runtime:
      hook: prompt-inject | data-source
      data: relative/path/to/file
      target: homophones | hallucinations | system_prompt

`prompt-inject` skills contribute extra text to the chat system prompt.
`data-source` skills load TOML/YAML/JSON into shared in-memory state
(homophones, hallucination filter, etc.).

Discovery searches the configured `[skills].search_paths` plus the bundled
`skills/` directory next to this package.
"""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

if sys.version_info >= (3, 11):
    import tomllib  # type: ignore
else:
    import tomli as tomllib  # type: ignore

from . import homophones, stt_filter


@dataclass
class Skill:
    name: str
    path: Path
    description: str = ""
    version: str = "0.0"
    runtime: dict = field(default_factory=dict)
    body: str = ""


def bundled_skills_dir() -> Path:
    """Where the package ships its own skills.

    Probe order:
    1. `_bundled/skills/` next to this file (wheel install via force-include)
    2. `../skills/` (legacy package-adjacent layout)
    3. `../../skills/` (dev checkout: ship/skills/)
    4. `<sys.prefix>/share/interview-assistant/skills/` (legacy shared-data)
    """
    here = Path(__file__).parent
    candidates = [
        here / "_bundled" / "skills",
        here.parent / "skills",
        here.parent.parent / "skills",
        Path(sys.prefix) / "share" / "interview-assistant" / "skills",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]


def parse_skill_md(md_path: Path) -> Skill | None:
    """Read a SKILL.md and parse its YAML frontmatter."""
    if not md_path.is_file():
        return None
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    fm: dict = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end > 0:
            try:
                fm = yaml.safe_load(text[4:end]) or {}
            except yaml.YAMLError:
                fm = {}
            body = text[end + 5:]
    return Skill(
        name=fm.get("name", md_path.parent.name),
        path=md_path.parent,
        description=fm.get("description", ""),
        version=str(fm.get("version", "0.0")),
        runtime=fm.get("runtime", {}) or {},
        body=body,
    )


def discover(search_paths: list[str]) -> list[Skill]:
    """Walk all search paths + the bundled dir, return all Skills found."""
    seen: dict[str, Skill] = {}
    paths = [Path(os.path.expanduser(p)).resolve() for p in search_paths]
    paths.append(bundled_skills_dir().resolve())
    for p in paths:
        if not p.is_dir():
            continue
        for md in p.glob("*/SKILL.md"):
            sk = parse_skill_md(md)
            if sk and sk.name not in seen:
                seen[sk.name] = sk
    return list(seen.values())


def apply_runtime_hooks(skills: list[Skill]) -> dict:
    """Execute each skill's `runtime` block. Returns a summary dict.

    Side effects:
      * homophones.PHONETIC_GROUPS is extended.
      * The returned `extra_hallucinations` list is meant to be fed into STTFilter.
      * The returned `prompt_injections` are appended to the system prompt.
    """
    summary = {"prompt_injections": [], "extra_hallucinations": [], "loaded": []}
    for sk in skills:
        rt = sk.runtime or {}
        hook = rt.get("hook", "")
        if hook == "prompt-inject":
            summary["prompt_injections"].append(_extract_inject_block(sk))
            summary["loaded"].append((sk.name, "prompt-inject", 1))
        elif hook == "data-source":
            data_rel = rt.get("data", "")
            target = rt.get("target", "")
            data_path = sk.path / data_rel if data_rel else None
            if data_path and data_path.is_file():
                count = _ingest_data_file(data_path, target, summary)
                summary["loaded"].append((sk.name, target or "data-source", count))
        # Always scan a `data/` subdirectory for any additional TOMLs that
        # carry their own `target = ...` declaration (multi-file skills).
        data_dir = sk.path / "data"
        if data_dir.is_dir():
            for extra in data_dir.glob("*.toml"):
                if rt.get("data") and (sk.path / rt["data"]).resolve() == extra.resolve():
                    continue
                target = _read_target_from_toml(extra)
                if target:
                    count = _ingest_data_file(extra, target, summary)
                    summary["loaded"].append((sk.name, target, count))
    return summary


def _read_target_from_toml(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return data.get("target", "")
    except Exception:
        return ""


def _extract_inject_block(sk: Skill) -> str:
    """Pull the body or a tagged section out of a SKILL.md as injection text."""
    body = sk.body
    m_start = body.find("<!-- INJECT-START -->")
    m_end = body.find("<!-- INJECT-END -->")
    if 0 <= m_start < m_end:
        return body[m_start + len("<!-- INJECT-START -->"):m_end].strip()
    return body.strip()[:1500]


def _ingest_data_file(path: Path, target: str, summary: dict) -> int:
    """Load a TOML data file into the right shared structure."""
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return 0

    entries = data.get("entry", [])
    count = 0

    if target == "homophones":
        extra: dict[str, list[str]] = {}
        for e in entries:
            canonical = e.get("canonical", "")
            variants = e.get("variants", []) + e.get("confusable", [])
            if canonical and variants:
                extra[canonical] = variants
                count += 1
        homophones.merge_groups(extra)

    elif target == "hallucinations":
        for e in entries:
            text = e.get("text", "")
            if text:
                summary["extra_hallucinations"].append(text)
                count += 1

    return count


def install(skill_dir: Path, target_dir: Path) -> Path:
    """Copy a skill directory into a target editor's skills folder."""
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / skill_dir.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(skill_dir, dest)
    return dest


def list_installed(search_paths: list[str]) -> list[tuple[Skill, Path]]:
    """Return (skill, install_path) for every skill under search_paths."""
    out: list[tuple[Skill, Path]] = []
    for p in search_paths:
        root = Path(os.path.expanduser(p)).resolve()
        if not root.is_dir():
            continue
        for md in root.glob("*/SKILL.md"):
            sk = parse_skill_md(md)
            if sk:
                out.append((sk, root))
    return out
