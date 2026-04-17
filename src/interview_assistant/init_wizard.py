"""Interactive `init` wizard. Always begins by asking the language."""
from __future__ import annotations

import os
import shutil
from copy import deepcopy
from pathlib import Path

from . import audio_backend, config as _cfg, doctor, i18n, network, providers, skills as _skills
from .theme import B, BCYN, BG_236, BGRN, BRED, BYEL, BWHT, DIM, RST, SAND, WARM


def _ascii_logo() -> str:
    return f"""
  {BG_236}{WARM}{B}                                                  {RST}
  {BG_236}{WARM}{B}              INTERVIEW  ASSISTANT                {RST}
  {BG_236}{SAND}             real-time STT  ·  hybrid RAG          {RST}
  {BG_236}{WARM}{B}                                                  {RST}
"""


def _ask(prompt: str, default: str = "", secret: bool = False) -> str:
    suffix = f" {DIM}[{default}]{RST}" if default else ""
    line = f"  {BCYN}?{RST} {prompt}{suffix}: "
    try:
        if secret:
            import getpass
            val = getpass.getpass(line.replace("\033", ""))
        else:
            val = input(line)
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return (val or default).strip()


def _ask_yn(prompt: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    while True:
        ans = _ask(f"{prompt} ({d})", "")
        if not ans:
            return default
        if ans.lower() in ("y", "yes", "是", "好", "ok"):
            return True
        if ans.lower() in ("n", "no", "否", "不"):
            return False


def _ask_choice(prompt: str, options: list[tuple[str, str]], default: int = 0) -> str:
    print(f"\n  {B}{prompt}{RST}")
    for i, (key, label) in enumerate(options, 1):
        marker = "→" if i - 1 == default else " "
        print(f"   {marker} {BCYN}{i}{RST}) {label}")
    while True:
        ans = _ask("", str(default + 1))
        try:
            n = int(ans)
            if 1 <= n <= len(options):
                return options[n - 1][0]
        except ValueError:
            pass


def _ask_multi(prompt: str, options: list[tuple[str, str, bool]]) -> list[str]:
    """Multi-select. Each option: (key, label, default_checked).

    Input format: '1 2 4' or '1,2,4'. Empty input keeps defaults.
    """
    print(f"\n  {B}{prompt}{RST}")
    for i, (key, label, checked) in enumerate(options, 1):
        mark = f"{BGRN}[x]{RST}" if checked else "[ ]"
        print(f"   {mark} {BCYN}{i}{RST}) {label}")
    print(f"   {DIM}(toggle: '1 3 5' or '1,3,5'; Enter keeps defaults){RST}")
    ans = _ask("", "")
    if not ans:
        return [k for k, _, c in options if c]
    raw = ans.replace(",", " ").split()
    selected = set()
    for tok in raw:
        try:
            n = int(tok)
            if 1 <= n <= len(options):
                selected.add(options[n - 1][0])
        except ValueError:
            pass
    return list(selected)


def _step_language() -> str:
    """Step 0: pick language. Always shown bilingually."""
    print()
    print("  Choose language / 请选择语言:")
    print(f"   {BCYN}1{RST}) 中文 (Chinese)")
    print(f"   {BCYN}2{RST}) English")
    while True:
        ans = input(f"  {BCYN}?{RST} [1]: ").strip() or "1"
        if ans in ("1", "中文", "zh", "zh-CN"):
            return "zh-CN"
        if ans in ("2", "english", "en", "EN"):
            return "en"


def _step_mode() -> str:
    """Returns one of: 'recall' | 'groq' | 'byo' | 'offline'."""
    print(f"\n  {DIM}{i18n.t('init.mode_recall_explain').strip()}{RST}")
    return _ask_choice(i18n.t("init.step_mode"), [
        ("recall",  i18n.t("init.mode_recall")),
        ("groq",    i18n.t("init.mode_groq")),
        ("byo",     i18n.t("init.mode_byo")),
        ("offline", i18n.t("init.mode_offline")),
    ], default=0)


def _step_network_check(target: str) -> str:
    """Probe connectivity to `target` (preset key like 'groq' / 'openai').

    Returns the proxy URL the user settled on (possibly empty if reachable
    directly or if user skipped). Side-effects: prints status.
    """
    provider_label = target
    print(f"\n  {DIM}{i18n.t('init.net_probe_internet')}{RST}", end=" ", flush=True)
    inet = network.probe(network.PROBE_URLS["internet"])
    if inet.ok:
        print(f"{BGRN}{i18n.t('init.net_ok', ms=inet.elapsed_ms)}{RST}")
    else:
        print(f"{BRED}{i18n.t('init.net_fail', err=inet.error[:60])}{RST}")

    print(f"  {DIM}{i18n.t('init.net_probe_target', provider=provider_label)}{RST}", end=" ", flush=True)
    tgt = network.probe(network.PROBE_URLS.get(target, network.PROBE_URLS["groq"]))
    if tgt.ok:
        print(f"{BGRN}{i18n.t('init.net_ok', ms=tgt.elapsed_ms)}{RST}")
        return ""

    print(f"{BRED}{i18n.t('init.net_fail', err=tgt.error[:60])}{RST}")
    print(f"\n  {BYEL}!{RST} {i18n.t('init.net_blocked_intro', provider=provider_label).strip()}\n")

    candidates: list[str] = []
    sysp = network.detect_system_proxy()
    if sysp:
        print(f"  {BCYN}→{RST} {i18n.t('init.net_proxy_detected_system', proxy=sysp)}")
        candidates.append(sysp)
    scanned = network.scan_local_proxy_ports()
    if scanned:
        print(f"  {BCYN}→{RST} {i18n.t('init.net_proxy_detected_scan')}")
        for p in scanned:
            print(f"      {p}")
        for p in scanned:
            if p not in candidates:
                candidates.append(p)

    for proxy in candidates:
        if _ask_yn(i18n.t("init.net_proxy_try", proxy=proxy), default=True):
            r = network.is_proxy_alive(proxy)
            if r.ok:
                print(f"  {BGRN}✓{RST} {i18n.t('init.net_proxy_ok')}")
                return proxy
            print(f"  {BYEL}!{RST} {i18n.t('init.net_proxy_bad')} ({r.error[:60]})")

    print(f"\n  {DIM}{i18n.t('init.net_proxy_help').strip()}{RST}\n")
    while True:
        manual = _ask(i18n.t("init.net_proxy_manual"), "")
        if not manual:
            return ""
        if not manual.startswith(("http://", "https://", "socks5://")):
            manual = "http://" + manual
        r = network.is_proxy_alive(manual)
        if r.ok:
            print(f"  {BGRN}✓{RST} {i18n.t('init.net_proxy_ok')}")
            return manual
        print(f"  {BYEL}!{RST} {i18n.t('init.net_proxy_bad')} ({r.error[:60]})")


def _step_chat_provider(cfg: dict, mode: str) -> dict:
    """Configure [chat] section based on selected mode."""
    print(f"\n  {B}{i18n.t('init.step_chat')}{RST}")

    if mode in ("recall", "offline"):
        cfg["chat"]["enabled"] = False
        cfg["chat"]["api_key"] = ""
        return cfg

    cfg["chat"]["enabled"] = True

    if mode == "groq":
        cfg["chat"]["base_url"] = providers.PRESETS["groq"]["base_url"]
        cfg["chat"]["model"] = providers.PRESETS["groq"]["model"]
        cfg["chat"]["fast_model"] = providers.PRESETS["groq"]["fast_model"]
        proxy = _step_network_check("groq")
        if proxy:
            cfg["chat"]["http_proxy"] = proxy
        print(f"  {DIM}{i18n.t('init.groq_url')}{RST}")
        key = _ask(i18n.t("init.enter_chat_key"), secret=True)
        if key:
            cfg["chat"]["api_key"] = key
            cfg["stt"]["groq_api_key"] = key
        return cfg

    presets = list(providers.PRESETS.keys())
    choice = _ask_choice("Pick provider preset", [(p, p) for p in presets] + [("custom", "custom")], default=0)
    if choice in providers.PRESETS:
        cfg["chat"]["base_url"] = providers.PRESETS[choice]["base_url"]
        cfg["chat"]["model"] = providers.PRESETS[choice]["model"]
        cfg["chat"]["fast_model"] = providers.PRESETS[choice]["fast_model"]
    cfg["chat"]["base_url"] = _ask(i18n.t("init.enter_chat_endpoint"), cfg["chat"]["base_url"])

    target_key = "openai" if "openai" in cfg["chat"]["base_url"] else "groq" if "groq" in cfg["chat"]["base_url"] else "internet"
    proxy = _step_network_check(target_key)
    if proxy:
        cfg["chat"]["http_proxy"] = proxy

    cfg["chat"]["api_key"] = _ask(i18n.t("init.enter_chat_key"), secret=True) or cfg["chat"]["api_key"]
    cfg["chat"]["model"] = _ask(i18n.t("init.enter_chat_model"), cfg["chat"]["model"])
    cfg["chat"]["fast_model"] = _ask(i18n.t("init.enter_fast_model"), cfg["chat"]["fast_model"])

    print(f"  {DIM}{i18n.t('init.test_connectivity')}{RST}")
    ok, err = providers.ping(cfg["chat"]["base_url"], cfg["chat"]["api_key"], cfg["chat"]["fast_model"], cfg["chat"].get("http_proxy", ""))
    if ok:
        print(f"  {BGRN}✓{RST} OK")
    else:
        print(f"  {BYEL}!{RST} {err[:140]}")
    return cfg


def _step_stt(cfg: dict, mode: str) -> dict:
    print(f"\n  {B}{i18n.t('init.step_stt')}{RST}")
    if mode == "offline":
        cfg["stt"]["provider"] = "local"
        cfg["stt"]["model"] = _ask("local model size (tiny/base/small/medium)", "small")
        return cfg

    if mode == "recall":
        sub = _ask_choice("STT for instant-recall mode", [
            ("groq",  "Groq Whisper (free, no credit card)"),
            ("local", "Local faster-whisper (fully offline)"),
        ], default=0)
        if sub == "local":
            cfg["stt"]["provider"] = "local"
            cfg["stt"]["model"] = _ask("local model size (tiny/base/small/medium)", "small")
            return cfg
        cfg["stt"]["provider"] = "groq"
        if not cfg["stt"].get("groq_api_key"):
            proxy = _step_network_check("groq")
            if proxy:
                cfg["chat"]["http_proxy"] = proxy
            print(f"  {DIM}{i18n.t('init.groq_url')}{RST}")
            cfg["stt"]["groq_api_key"] = _ask(i18n.t("init.enter_groq_key"), secret=True)
        return cfg

    if mode == "groq":
        cfg["stt"]["provider"] = "groq"
        # Reuse the same Groq key for STT if user already set chat.api_key
        if not cfg["stt"].get("groq_api_key") and cfg["chat"].get("api_key"):
            cfg["stt"]["groq_api_key"] = cfg["chat"]["api_key"]
        return cfg

    cfg["stt"]["provider"] = _ask("STT provider (groq | deepgram | local)", "groq")
    if cfg["stt"]["provider"] == "groq" and not cfg["stt"].get("groq_api_key"):
        print(f"  {DIM}{i18n.t('init.groq_url')}{RST}")
        cfg["stt"]["groq_api_key"] = _ask(i18n.t("init.enter_groq_key"), secret=True)
    elif cfg["stt"]["provider"] == "deepgram":
        cfg["stt"]["deepgram_api_key"] = _ask("Deepgram API key", secret=True)
    return cfg


def _step_knowledge(cfg: dict) -> None:
    print(f"\n  {B}{i18n.t('init.step_kb')}{RST}")
    kb_dir = Path("./knowledge").resolve()
    kb_dir.mkdir(parents=True, exist_ok=True)
    existing = list(kb_dir.glob("*.md"))
    if existing:
        print(f"  {DIM}{i18n.t('init.kb_existing', n=len(existing))}{RST}")
    starter_dest = kb_dir / "00_starter.md"
    if not starter_dest.exists():
        if _ask_yn(i18n.t("init.kb_copy_starter"), default=True):
            src = _starter_template_path()
            if src and src.exists():
                shutil.copy(src, starter_dest)
                print(f"  {BGRN}✓{RST} {starter_dest}")
    gi = kb_dir / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n!.gitignore\n!00_starter.md\n", encoding="utf-8")


def _starter_template_path() -> Path | None:
    here = Path(__file__).parent
    for c in [
        here / "_bundled" / "templates" / "knowledge.starter.md",
        here.parent / "templates" / "knowledge.starter.md",
        here.parent.parent / "templates" / "knowledge.starter.md",
        Path(os.sys.prefix) / "share" / "interview-assistant" / "templates" / "knowledge.starter.md",
    ]:
        if c.is_file():
            return c
    return None


def _step_skills(cfg: dict) -> None:
    print(f"\n  {B}{i18n.t('init.step_skills')}{RST}")
    bundled = _skills.bundled_skills_dir()
    if not bundled.is_dir():
        print(f"  {BYEL}!{RST} no bundled skills found at {bundled}")
        return

    available = sorted(bundled.glob("*/SKILL.md"))
    if not available:
        return

    has_cursor = (Path.home() / ".cursor").exists()
    has_claude = (Path.home() / ".claude").exists()

    targets = _ask_multi(i18n.t("init.skills_targets"), [
        ("./.cursor/skills", i18n.t("init.skills_target_cursor_local"), True),
        (str(Path.home() / ".cursor/skills"), i18n.t("init.skills_target_cursor_user"), False),
        ("./.claude/skills", i18n.t("init.skills_target_claude_local"), has_claude),
        (str(Path.home() / ".claude/skills"), i18n.t("init.skills_target_claude_user"), False),
    ])

    for sk_md in available:
        sk_dir = sk_md.parent
        for tgt in targets:
            target_dir = Path(os.path.expanduser(tgt)).resolve()
            try:
                dest = _skills.install(sk_dir, target_dir)
                print(f"  {BGRN}✓{RST} {sk_dir.name} → {dest}")
            except Exception as e:
                print(f"  {BRED}✗{RST} {sk_dir.name} → {target_dir}: {e}")


def _step_ptt(cfg: dict) -> None:
    sysname = audio_backend.system()
    options = [
        ("alt_r", i18n.t("init.ptt_alt_r")),
        ("f8", i18n.t("init.ptt_f8")),
        ("cmd_r", i18n.t("init.ptt_cmd_r")),
        ("ctrl_r", i18n.t("init.ptt_ctrl_r")),
        ("f5", i18n.t("init.ptt_f5") + ("  ⚠" if sysname == "Darwin" else "")),
    ]
    cfg["hotkey"]["ptt"] = _ask_choice(i18n.t("init.ptt_prompt"), options, default=0)


def _step_audio_summary(cfg: dict) -> None:
    print(f"\n  {B}{i18n.t('init.step_audio')}{RST}")
    lb = audio_backend.find_loopback()
    mic = audio_backend.find_microphone()
    if lb.id is not None:
        print(f"  {BGRN}✓{RST} {i18n.t('run.audio_sys', name=lb.name, id=lb.id)}")
    else:
        print(f"  {BYEL}!{RST} {i18n.t('run.audio_sys_none')}")
    if mic.id is not None:
        print(f"  {BGRN}✓{RST} {i18n.t('run.audio_mic', name=mic.name, id=mic.id)}")
    else:
        print(f"  {BYEL}!{RST} {i18n.t('run.audio_mic_none')}")


def run() -> int:
    """Run the full wizard. Returns 0 on success."""
    lang = _step_language()
    i18n.set_language(lang)

    print(_ascii_logo())
    print(f"  {B}{i18n.t('init.welcome')}{RST}")
    print(f"  {DIM}{i18n.t('init.welcome_sub')}{RST}\n")

    cfg = deepcopy(_cfg.DEFAULTS)
    cfg["ui"]["lang"] = lang

    mode = _step_mode()
    print(f"\n  {B}{i18n.t('init.step_doctor')}{RST}")
    doctor.run(cfg, autofix=False)

    cfg = _step_chat_provider(cfg, mode)
    cfg = _step_stt(cfg, mode)
    _step_ptt(cfg)
    _step_knowledge(cfg)
    _step_skills(cfg)
    _step_audio_summary(cfg)

    saved = _cfg.save(cfg)
    print(f"\n  {BGRN}✓{RST} {i18n.t('common.done')} → {saved}")
    if not cfg["chat"].get("enabled"):
        print(f"  {DIM}{i18n.t('run.mode_recall_only')}{RST}")
    print()
    print(f"  {B}{i18n.t('init.done_quickstart_title')}{RST}\n")
    print(i18n.t("init.done_quickstart"))
    return 0
