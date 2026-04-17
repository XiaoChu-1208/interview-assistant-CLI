"""Top-level CLI: `interview-assistant` / `ia` entry point."""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import sys
import threading
from pathlib import Path

from . import (
    __version__,
    audio_backend,
    config as _cfg,
    doctor as _doctor,
    i18n,
    init_wizard,
    qa as _qa,
    rag,
    skills as _skills,
    stt_filter,
    homophones,
)
from .theme import (
    B, BBLU, BCYN, BG_236, BGRN, BRED, BWHT, BYEL, DIM, RST, SAND, WARM, term_width,
)


def _header():
    w = 52
    print()
    print(f"  {BG_236}{WARM}{B}{'':^{w}}{RST}")
    print(f"  {BG_236}{WARM}{B}{'INTERVIEW ASSISTANT':^{w}}{RST}")
    print(f"  {BG_236}{SAND}{i18n.t('app.tagline', version=__version__):^{w}}{RST}")
    print(f"  {BG_236}{WARM}{B}{'':^{w}}{RST}")
    print()


# ─────────────────────────── run (default) ───────────────────


def cmd_run(args) -> int:
    cfg = _cfg.load()
    i18n.set_language(cfg["ui"].get("lang") or None)

    has_chat = _cfg.has_chat_creds(cfg)
    has_stt = _cfg.has_stt_creds(cfg) or cfg["stt"]["provider"] == "local"

    if not has_chat and not has_stt and not _cfg.config_path().exists():
        print(f"\n  {BYEL}!{RST} no config — run `interview-assistant init` first\n")
        return 1

    _header()

    print(f"{DIM}  {i18n.t('run.loading_kb')}{RST}", end=" ", flush=True)
    sections = rag.load_documents(cfg["knowledge"]["dirs"])
    bm25_index = rag.build_bm25_index(sections) if sections else {"idf": {}, "avg_len": 1}
    print(f"{BGRN}{B}{len(sections)}{RST} {DIM}{i18n.t('run.loaded_kb', n=len(sections)).split(' ', 1)[-1]}{RST}")

    print(f"{DIM}  {i18n.t('run.loading_embed')}{RST}", end=" ", flush=True)
    embedder = rag.init_embedder()
    doc_embeddings = None
    if embedder is not None:
        try:
            doc_embeddings = rag.get_or_build_embeddings(sections, embedder)
            n = doc_embeddings.shape[0] if doc_embeddings is not None else 0
            d = doc_embeddings.shape[1] if doc_embeddings is not None else 0
            print(f"{BGRN}ok{RST} {DIM}({n} vectors, dim={d}){RST}")
        except Exception as e:
            embedder = None
            print(f"{BYEL}{i18n.t('run.embed_degraded', err=e)}{RST}")
    else:
        print(f"{BYEL}{i18n.t('run.embed_degraded', err='fastembed not installed')}{RST}")

    qhint_secs, qhint_embs = rag.build_qhint_index(sections, embedder)
    print(f"{DIM}  {i18n.t('run.recall_idx', n=len(qhint_secs))}{RST}")
    if has_chat:
        print(f"{DIM}  {i18n.t('run.llm_backend', model=cfg['chat']['model'])}{RST}")
    else:
        print(f"{DIM}  {i18n.t('run.mode_recall_only')}{RST}")

    # Skills
    skills = _skills.discover(cfg["skills"]["search_paths"])
    summary = _skills.apply_runtime_hooks(skills)
    sf = stt_filter.STTFilter(
        extra_hallucinations=summary["extra_hallucinations"] + cfg["stt_filter"]["extra_hallucinations"],
        extra_fillers=cfg["stt_filter"]["extra_fillers"],
    )
    system_prompt = _qa.build_system_prompt(summary["prompt_injections"])

    for name, kind, count in summary["loaded"]:
        print(f"{DIM}  {i18n.t('skills.scan_ok', name=name, n=count)}{RST}")

    # Audio
    lb = audio_backend.find_loopback()
    mic = audio_backend.find_microphone()
    if lb.id is not None:
        print(f"{DIM}  {i18n.t('run.audio_sys', name=lb.name, id=lb.id)}{RST}")
    else:
        print(f"{BYEL}  {i18n.t('run.audio_sys_none')}{RST}")
    if mic.id is not None:
        print(f"{DIM}  {i18n.t('run.audio_mic', name=mic.name, id=mic.id)}{RST}")
    else:
        print(f"{BYEL}  {i18n.t('run.audio_mic_none')}{RST}")

    print()
    print(f"{DIM}  hold {cfg['hotkey']['ptt']:<6} push-to-talk via mic{RST}")
    print(f"{DIM}{i18n.t('run.hint_listen')}{RST}")
    print(f"{DIM}{i18n.t('run.hint_off')}{RST}")
    print(f"{DIM}{i18n.t('run.hint_search')}{RST}")
    print(f"{DIM}{i18n.t('run.hint_reload')}{RST}")
    print(f"{DIM}{i18n.t('run.hint_quit')}{RST}")
    print(f"{DIM}{'─' * term_width()}{RST}")

    listener_state = {"obj": None, "mode": "off"}
    chat_history: list[dict] = []
    active_query = [""]
    gen_id = [0]

    def on_transcript(text, source="interviewer"):
        gen_id[0] += 1
        my_id = gen_id[0]
        if source == "you":
            print(f"\n{WARM}{B}  you{RST}  {text}", flush=True)
        else:
            print(f"\n{BBLU}{B}  interviewer{RST}  {text}", flush=True)
        active_query[0] = text

        def _process():
            q_out, a_out = _qa.handle_question(
                text, sections, bm25_index, cfg,
                embedder=embedder, doc_embeddings=doc_embeddings,
                qhint_sections=qhint_secs, qhint_embeddings=qhint_embs,
                chat_history=chat_history, system_prompt=system_prompt,
            )
            if a_out:
                chat_history.append({"q": q_out, "a": a_out})
                if len(chat_history) > 6:
                    del chat_history[:-6]
            if my_id == gen_id[0]:
                print(f"{BCYN}  > {RST}", end="", flush=True)

        threading.Thread(target=_process, daemon=True).start()

    def _switch_listener(target):
        if listener_state["obj"]:
            try:
                listener_state["obj"].stop()
            except Exception:
                pass
            listener_state["obj"] = None
        if target == "off":
            listener_state["mode"] = "off"
            print(f"{DIM}  listener off{RST}\n")
            return
        if target == "listen":
            if lb.id is None:
                print(f"{BRED}  no system-audio device{RST}\n")
                return
            from .audio import AudioListener
            try:
                ls = AudioListener(lb.id, on_transcript, cfg, sf)
                ls.start()
                listener_state["obj"] = ls
                listener_state["mode"] = "listen"
                print(f"\n{BGRN}  Listen mode{RST} {DIM}— {lb.name}{RST}\n")
            except Exception as e:
                print(f"\n{BRED}  audio failed: {e}{RST}\n")

    if lb.id is not None:
        _switch_listener("listen")

    # PTT
    ptt_recorder = None
    try:
        from pynput import keyboard as kb
    except ImportError:
        kb = None

    if mic.id is not None and kb is not None:
        from .audio import PushToTalkRecorder
        try:
            ptt_recorder = PushToTalkRecorder(mic.id, on_transcript, cfg, sf)
            held = [False]
            target_key = _resolve_ptt_key(cfg["hotkey"]["ptt"], kb)

            def _is_match(key):
                if target_key == kb.Key.alt_r:
                    return key in (kb.Key.alt_r, getattr(kb.Key, "alt_gr", kb.Key.alt_r))
                return key == target_key

            def _on_press(k):
                try:
                    if _is_match(k) and not held[0]:
                        held[0] = True
                        ptt_recorder.start()
                except Exception:
                    pass

            def _on_release(k):
                try:
                    if _is_match(k) and held[0]:
                        held[0] = False
                        ptt_recorder.stop()
                except Exception:
                    pass

            listener = kb.Listener(on_press=_on_press, on_release=_on_release)
            listener.daemon = True
            listener.start()
        except Exception as e:
            print(f"{BYEL}  PTT disabled: {e}{RST}\n")

    def _shutdown(*_):
        print(f"\n{DIM}  {i18n.t('run.shutting_down')}{RST}", flush=True)
        if listener_state["obj"]:
            try:
                listener_state["obj"].stop()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)

    while True:
        try:
            query = input(f"{BCYN}  > {RST}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}  {i18n.t('run.bye')}{RST}\n")
            break
        if not query:
            continue
        if query.lower() in ("q", "quit", "exit"):
            print(f"{DIM}  {i18n.t('run.bye')}{RST}\n")
            break
        ql = query.lower().lstrip("/")
        if ql in ("listen", "off"):
            _switch_listener(ql)
            continue
        if query == "/reload":
            print(f"{DIM}  {i18n.t('run.reloading')}{RST}", end=" ", flush=True)
            sections = rag.load_documents(cfg["knowledge"]["dirs"])
            bm25_index = rag.build_bm25_index(sections) if sections else {"idf": {}, "avg_len": 1}
            if embedder is not None:
                doc_embeddings = rag.get_or_build_embeddings(sections, embedder)
            qhint_secs, qhint_embs = rag.build_qhint_index(sections, embedder)
            print(f"{BGRN}{len(sections)}{RST} {DIM}sections{RST}")
            continue
        if query.startswith("/search "):
            kw = query[8:].strip()
            results = rag.search_documents(kw, sections, bm25_index, embedder, doc_embeddings, top_k=10)
            if not results:
                print(f"{DIM}  {i18n.t('run.no_results')}{RST}\n")
                continue
            for i, (s, sec) in enumerate(results, 1):
                print(f"  {DIM}{i}.{RST} {sec['title'][:65]}")
                print(f"     {DIM}{sec['content'].replace(chr(10), ' ')[:120]}...{RST}")
            print()
            continue

        _qa.handle_question(
            query, sections, bm25_index, cfg,
            embedder=embedder, doc_embeddings=doc_embeddings,
            qhint_sections=qhint_secs, qhint_embeddings=qhint_embs,
            chat_history=chat_history, system_prompt=system_prompt,
        )

    if listener_state["obj"]:
        try:
            listener_state["obj"].stop()
        except Exception:
            pass
    return 0


def _resolve_ptt_key(name: str, kb):
    name = name.lower()
    table = {
        "alt_r": kb.Key.alt_r, "alt": kb.Key.alt_r,
        "f5": kb.Key.f5, "f6": kb.Key.f6, "f7": kb.Key.f7, "f8": kb.Key.f8,
        "cmd_r": kb.Key.cmd_r, "ctrl_r": kb.Key.ctrl_r,
        "shift_r": kb.Key.shift_r,
    }
    return table.get(name, kb.Key.alt_r)


# ─────────────────────────── ask (dry-run) ─────────────────


def cmd_ask(args) -> int:
    cfg = _cfg.load()
    i18n.set_language(cfg["ui"].get("lang") or None)
    sections = rag.load_documents(cfg["knowledge"]["dirs"])
    if not sections:
        print(f"  {BYEL}!{RST} no knowledge — run `interview-assistant init` first\n")
        return 1
    bm25_index = rag.build_bm25_index(sections)
    embedder = rag.init_embedder()
    doc_embs = rag.get_or_build_embeddings(sections, embedder) if embedder else None
    qhint_secs, qhint_embs = rag.build_qhint_index(sections, embedder)

    skills = _skills.discover(cfg["skills"]["search_paths"])
    summary = _skills.apply_runtime_hooks(skills)
    system_prompt = _qa.build_system_prompt(summary["prompt_injections"])

    print(f"\n{BBLU}{B}  Q{RST}  {args.question}\n")
    results = rag.search_documents(args.question, sections, bm25_index, embedder, doc_embs, top_k=5)
    print(f"{DIM}  Top retrieved:{RST}")
    for i, (s, sec) in enumerate(results, 1):
        print(f"   {DIM}{i}. ({s:.2f}){RST} {sec['title'][:65]}")
    print()

    _qa.handle_question(
        args.question, sections, bm25_index, cfg,
        embedder=embedder, doc_embeddings=doc_embs,
        qhint_sections=qhint_secs, qhint_embeddings=qhint_embs,
        system_prompt=system_prompt,
    )
    return 0


# ─────────────────────────── doctor ────────────────────────


def cmd_doctor(args) -> int:
    cfg = _cfg.load()
    i18n.set_language(cfg["ui"].get("lang") or None)
    _doctor.run(cfg, autofix=args.fix)
    return 0


# ─────────────────────────── init ──────────────────────────


def cmd_init(args) -> int:
    return init_wizard.run()


# ─────────────────────────── skills ────────────────────────


def cmd_skills_install(args) -> int:
    cfg = _cfg.load()
    bundled = _skills.bundled_skills_dir()
    if not bundled.is_dir():
        print(f"{BRED}  no bundled skills found{RST}")
        return 1
    target_root = Path(args.target).expanduser().resolve() if args.target else Path("./.cursor/skills").resolve()
    available = sorted(bundled.glob("*/SKILL.md"))
    for sk_md in available:
        sk_dir = sk_md.parent
        if args.name and sk_dir.name != args.name:
            continue
        try:
            dest = _skills.install(sk_dir, target_root)
            print(f"  {BGRN}✓{RST} {sk_dir.name} → {dest}")
        except Exception as e:
            print(f"  {BRED}✗{RST} {sk_dir.name}: {e}")
    return 0


def cmd_skills_list(args) -> int:
    cfg = _cfg.load()
    found = _skills.list_installed(cfg["skills"]["search_paths"])
    if not found:
        print(f"  {DIM}no skills installed in any search path{RST}")
        return 0
    for sk, root in found:
        print(f"  {BGRN}{sk.name}{RST} {DIM}v{sk.version} — {sk.path}{RST}")
    return 0


def cmd_skills_upgrade(args) -> int:
    cfg = _cfg.load()
    bundled = _skills.bundled_skills_dir()
    bundled_skills = {sk.name: sk for sk in (_skills.parse_skill_md(p) for p in bundled.glob("*/SKILL.md")) if sk}
    found = _skills.list_installed(cfg["skills"]["search_paths"])
    for sk, root in found:
        latest = bundled_skills.get(sk.name)
        if not latest:
            continue
        if latest.version > sk.version:
            print(f"  {BCYN}↑{RST} {i18n.t('skills.upgrade_available', name=sk.name, old=sk.version, new=latest.version)}")
            try:
                _skills.install(latest.path, sk.path.parent)
                print(f"    {BGRN}✓{RST} upgraded")
            except Exception as e:
                print(f"    {BRED}✗{RST} {e}")
    return 0


def cmd_skills_uninstall(args) -> int:
    cfg = _cfg.load()
    found = _skills.list_installed(cfg["skills"]["search_paths"])
    for sk, root in found:
        if sk.name == args.name:
            try:
                shutil.rmtree(sk.path)
                print(f"  {BGRN}✓{RST} {i18n.t('skills.uninstalled', name=sk.name, path=sk.path)}")
            except Exception as e:
                print(f"  {BRED}✗{RST} {e}")
    return 0


# ─────────────────────────── knowledge ─────────────────────


def cmd_knowledge_validate(args) -> int:
    cfg = _cfg.load()
    from .knowledge_tools import validate_dirs
    return validate_dirs(cfg["knowledge"]["dirs"], fix=args.fix)


def cmd_knowledge_status(args) -> int:
    cfg = _cfg.load()
    from .knowledge_tools import status_dirs
    return status_dirs(cfg["knowledge"]["dirs"])


def cmd_knowledge_new(args) -> int:
    cfg = _cfg.load()
    from .knowledge_tools import interactive_new
    return interactive_new(cfg)


def cmd_knowledge_ingest(args) -> int:
    cfg = _cfg.load()
    from .knowledge_tools import ingest_file
    return ingest_file(cfg, args.path)


# ─────────────────────────── argparse ──────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="interview-assistant",
        description="Real-time interview copilot.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("init", help="Run the interactive setup wizard")

    p_run = sub.add_parser("run", help="Start the live assistant (default)")
    p_run.set_defaults(func=cmd_run)

    p_ask = sub.add_parser("ask", help="Dry-run a single question (no audio)")
    p_ask.add_argument("question", help="The interview question to test")
    p_ask.set_defaults(func=cmd_ask)

    p_doc = sub.add_parser("doctor", help="Diagnose environment")
    p_doc.add_argument("--fix", action="store_true", help="Attempt auto-fix")
    p_doc.set_defaults(func=cmd_doctor)

    p_sk = sub.add_parser("skills", help="Manage installed skills")
    sk_sub = p_sk.add_subparsers(dest="sk_cmd")
    p_sk_i = sk_sub.add_parser("install"); p_sk_i.add_argument("--target", default=""); p_sk_i.add_argument("--name", default=""); p_sk_i.set_defaults(func=cmd_skills_install)
    sk_sub.add_parser("list").set_defaults(func=cmd_skills_list)
    sk_sub.add_parser("upgrade").set_defaults(func=cmd_skills_upgrade)
    p_sk_u = sk_sub.add_parser("uninstall"); p_sk_u.add_argument("name"); p_sk_u.set_defaults(func=cmd_skills_uninstall)

    p_kb = sub.add_parser("knowledge", help="Manage knowledge base")
    kb_sub = p_kb.add_subparsers(dest="kb_cmd")
    p_kb_v = kb_sub.add_parser("validate"); p_kb_v.add_argument("--fix", action="store_true"); p_kb_v.set_defaults(func=cmd_knowledge_validate)
    kb_sub.add_parser("status").set_defaults(func=cmd_knowledge_status)
    kb_sub.add_parser("new").set_defaults(func=cmd_knowledge_new)
    p_kb_i = kb_sub.add_parser("ingest"); p_kb_i.add_argument("path"); p_kb_i.set_defaults(func=cmd_knowledge_ingest)

    args = parser.parse_args()

    if args.cmd is None:
        return cmd_run(args)
    if args.cmd == "init":
        return cmd_init(args)
    if args.cmd == "skills" and not getattr(args, "sk_cmd", None):
        cmd_skills_list(args); return 0
    if args.cmd == "knowledge" and not getattr(args, "kb_cmd", None):
        cmd_knowledge_status(args); return 0

    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    return func(args)
