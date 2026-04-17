"""Knowledge base helpers: validate, status, interactive new, file ingest.

Validation is structural: each file must have at least one `## ` heading, each
Q&A entry should have `Q:` + `A:`, and any tree block must use `\`\`\`tree`.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from . import config as _cfg, i18n, providers
from .theme import B, BCYN, BGRN, BRED, BYEL, DIM, RST


_Q_PAT = re.compile(r"^\*{0,2}[Qq问题]{1,2}[：:.]\s*", re.MULTILINE)
_A_PAT = re.compile(r"^\*{0,2}[Aa答案]{1,2}[：:.]\s*", re.MULTILINE)


def _validate_file(path: Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    text = path.read_text(encoding="utf-8")

    if not text.strip():
        errors.append("file is empty")
        return errors, warnings

    if not re.search(r"^#{1,4} ", text, re.MULTILINE):
        warnings.append("no markdown headings — RAG splits by `## `")

    qs = _Q_PAT.findall(text)
    if qs and not _A_PAT.findall(text):
        warnings.append("found Q: lines but no A: lines")

    for m in re.finditer(r"```([a-zA-Z]*)\n", text):
        lang = m.group(1)
        if lang and lang not in ("tree", "python", "yaml", "json", "toml", "bash", "sql", "md", "markdown", "text"):
            warnings.append(f"unknown code block lang: {lang!r}")
            break

    if "[需补充]" in text or "[TBD]" in text or "[FILL ME]" in text:
        warnings.append("contains TBD placeholder — please complete")

    return errors, warnings


def validate_dirs(dirs: list[str], fix: bool = False) -> int:
    total_errors = 0
    for d in dirs:
        root = Path(os.path.expanduser(d)).resolve()
        if not root.is_dir():
            print(f"  {BYEL}!{RST} no such dir: {root}")
            continue
        for p in sorted(root.glob("*.md")):
            errs, warns = _validate_file(p)
            total_errors += len(errs)
            if errs:
                print(f"  {BRED}✗{RST} {i18n.t('knowledge.validate_err', file=p.name, n=len(errs))}")
                for e in errs:
                    print(f"      {BRED}-{RST} {e}")
            elif warns:
                print(f"  {BYEL}!{RST} {i18n.t('knowledge.validate_warn', file=p.name, n=len(warns))}")
                for w in warns:
                    print(f"      {BYEL}-{RST} {w}")
            else:
                print(f"  {BGRN}✓{RST} {i18n.t('knowledge.validate_ok', file=p.name)}")
    return 0 if total_errors == 0 else 2


def status_dirs(dirs: list[str]) -> int:
    counts = {"approved": 0, "draft": 0, "invalid": 0}
    for d in dirs:
        root = Path(os.path.expanduser(d)).resolve()
        if not root.is_dir():
            continue
        for p in sorted(root.glob("*.md")):
            if p.name.startswith("draft_"):
                counts["draft"] += 1
                bucket = "draft"
                color = BYEL
            else:
                errs, _ = _validate_file(p)
                if errs:
                    counts["invalid"] += 1
                    bucket, color = "invalid", BRED
                else:
                    counts["approved"] += 1
                    bucket, color = "approved", BGRN
            print(f"  {color}{bucket:>8}{RST}  {p}")
    print()
    print(f"  {BGRN}{counts['approved']}{RST} approved   {BYEL}{counts['draft']}{RST} draft   {BRED}{counts['invalid']}{RST} invalid")
    return 0


def interactive_new(cfg: dict) -> int:
    """Walk the user through creating one Q&A entry."""
    print(f"\n  {B}Add a new Q&A entry{RST}\n  {DIM}(blank line to stop adding answers, Ctrl-C to abort){RST}\n")
    topic = input(f"  {BCYN}?{RST} Topic / file name (e.g. 'about_me'): ").strip()
    if not topic:
        return 1
    q = input(f"  {BCYN}?{RST} Question: ").strip()
    if not q:
        return 1
    print(f"  {DIM}Answer (multiple lines, blank line to finish):{RST}")
    lines: list[str] = []
    while True:
        try:
            line = input("  ")
        except EOFError:
            break
        if not line:
            break
        lines.append(line)
    if not lines:
        return 1
    answer = "\n".join(lines)

    target_dir = Path(os.path.expanduser(cfg["knowledge"]["dirs"][0])).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    fname = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff-]+", "_", topic)
    target = target_dir / f"{fname}.md"
    section_md = f"\n## {q}\n\n**Q:** {q}\n\n**A:**\n\n{answer}\n"
    if target.exists():
        with open(target, "a", encoding="utf-8") as f:
            f.write(section_md)
    else:
        with open(target, "w", encoding="utf-8") as f:
            f.write(f"# {topic}\n{section_md}")
    print(f"\n  {BGRN}✓{RST} {target}\n")
    return 0


def ingest_file(cfg: dict, path: str) -> int:
    """LLM-assisted: read PDF/DOCX/MD/TXT and produce a draft Q&A markdown."""
    src = Path(path).expanduser().resolve()
    if not src.is_file():
        print(f"  {BRED}✗{RST} no such file: {src}")
        return 1

    text = _read_source(src)
    if not text:
        print(f"  {BRED}✗{RST} cannot extract text from {src.name}")
        return 1

    print(f"  {DIM}{i18n.t('knowledge.ingest_estimating')}{RST}")
    tokens_estimate = len(text) // 3
    cost_estimate = "<$0.01" if tokens_estimate < 5000 else f"~${tokens_estimate * 0.6 / 1_000_000:.2f}"
    print(f"  {DIM}{i18n.t('knowledge.ingest_cost', tokens=tokens_estimate, cost=cost_estimate)}{RST}")
    ans = input(f"  {BCYN}?{RST} (y/N): ").strip().lower()
    if ans not in ("y", "yes"):
        print(f"  {DIM}cancelled{RST}")
        return 0

    if not _cfg.has_chat_creds(cfg):
        print(f"  {BRED}✗{RST} no chat API key configured. Run `interview-assistant init`.")
        return 1

    system = (
        "You convert résumés / interview prep notes into a Markdown Q&A file "
        "for the `interview-knowledge-format` skill. Output ONLY the markdown.\n\n"
        "Format:\n"
        "# <topic>\n"
        "## <question>\n"
        "**Q:** <question>\n"
        "**A:**\n"
        "<concise STAR answer in user's voice, 4-8 sentences>\n\n"
        "Rules: extract one Q&A per topic. If something is missing in the source, "
        "use `[需补充]` instead of inventing facts. Use the user's first person."
    )
    prompt = f"Source: {src.name}\n\n{text[:20000]}"
    try:
        full = providers.chat(
            cfg["chat"], [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            stream=False, max_tokens=4000, temperature=0.2,
        )
    except Exception as e:
        print(f"  {BRED}✗{RST} llm error: {e}")
        return 1

    if not isinstance(full, str):
        full = "".join(full)

    target_dir = Path(os.path.expanduser(cfg["knowledge"]["dirs"][0])).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    fname = "draft_" + re.sub(r"[^a-zA-Z0-9_-]+", "_", src.stem) + ".md"
    target = target_dir / fname
    header = i18n.t("knowledge.draft_header")
    target.write_text(header + "\n\n" + full.strip() + "\n", encoding="utf-8")
    print(f"  {BGRN}✓{RST} {i18n.t('knowledge.ingest_writing', path=target)}")
    print(f"  {DIM}rename to drop the `draft_` prefix once reviewed{RST}")
    return 0


def _read_source(path: Path) -> str:
    suf = path.suffix.lower()
    if suf in (".md", ".txt"):
        return path.read_text(encoding="utf-8", errors="ignore")
    if suf == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            print(f"  {BYEL}!{RST} pip install 'interview-assistant[ingest]' for PDF support")
            return ""
        try:
            reader = PdfReader(str(path))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:
            print(f"  {BRED}✗{RST} pdf read failed: {e}")
            return ""
    if suf == ".docx":
        try:
            import docx
        except ImportError:
            print(f"  {BYEL}!{RST} pip install 'interview-assistant[ingest]' for DOCX support")
            return ""
        try:
            d = docx.Document(str(path))
            return "\n".join(p.text for p in d.paragraphs)
        except Exception as e:
            print(f"  {BRED}✗{RST} docx read failed: {e}")
            return ""
    return path.read_text(encoding="utf-8", errors="ignore")
