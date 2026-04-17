# Interview Assistant

> A real-time interview copilot that hears the question and shows you **the answer you already prepared** — verbatim, in milliseconds.

[![PyPI](https://img.shields.io/pypi/v/interview-assistant?color=blue)](https://pypi.org/project/interview-assistant/)
[![Python](https://img.shields.io/pypi/pyversions/interview-assistant.svg)](https://pypi.org/project/interview-assistant/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)](#platform-notes)
[![GitHub stars](https://img.shields.io/github/stars/XiaoChu-1208/interview-assistant-CLI?style=social)](https://github.com/XiaoChu-1208/interview-assistant-CLI)

[简体中文](./README.zh-CN.md) · English

**Keywords**: real-time interview assistant · instant recall · Whisper STT · BM25 + embeddings hybrid RAG · Cursor skill · Claude Code skill · Codex skill · local-first knowledge base · Groq · OpenAI-compatible · push-to-talk · macOS · Windows · Linux · 实时面试助手 · 本地知识库检索 · 多音字过滤 · 中转代理自动检测

---

## Why this exists (and why it's different)

Most "AI interview helper" projects on GitHub do roughly the same thing: pipe the interviewer's audio into Whisper, paste the transcription into GPT-4 / Claude, and stream the model's freshly-generated answer back to the candidate.

That approach **does not actually work in a real interview**, for four reasons:

| Problem with LLM-only tools | What actually happens |
|---|---|
| **Latency** | 2–6 s for the first useful token. The interviewer is already onto follow-ups. |
| **It's not your voice** | The LLM outputs polished generic English / Chinese; you sound like you're reading. Interviewers notice immediately. |
| **Hallucination** | The LLM invents projects, metrics, team sizes, dates you don't actually have. You can't recover from "Wait, you said 23%, where's that number from?". |
| **Per-question cost & rate limits** | Right when you most need 100% reliability, you hit a 429 or run out of credit. |

### The Instant-Recall approach

Interview Assistant inverts the design:

> **You prepare the answers in advance. The tool's only job is to find the right one fast.**

Concretely, in a live interview:

1. Whisper transcribes the interviewer's question.
2. Hybrid retrieval (BM25 + dense embeddings) finds the closest entry in **your local Markdown knowledge base** — which contains answers *you* wrote, in *your* voice, with *your* real numbers.
3. If the match is strong, the assistant prints **your stored answer verbatim** — no LLM call, no rephrasing, no hallucination, often under 200 ms after the question ends.
4. If the match is weak (and only then), it can optionally fall back to an LLM grounded on the same retrieved context — but this is the failure path, not the main path.

The trade-off is honest: **you have to do the prep work**. There is no free lunch where an LLM gives you good interview answers about a life it doesn't know. What this tool gives you is *leverage on your prep*: your study time becomes a permanent searchable corpus, and the next interview reuses it instantly.

To make the prep itself manageable, the project ships with a Cursor / Claude Code / Codex skill (`interview-knowledge-format`) that converts your résumé / past interview transcripts / job descriptions into the right Q&A format automatically.

---

## Highlights

### Primary

- **Instant Recall is a first-class mode.** You can run the entire app with the chat-LLM completely disabled. Whisper + your knowledge base. That's it. No hallucination surface area, no per-token cost, no API outage to worry about mid-interview.
- **Your answers, verbatim.** The retrieval layer is tuned to *prefer printing your stored text exactly* over rewriting it. You hear what you wrote. You sound like yourself.
- **Predictable latency.** Sub-second from end-of-question to on-screen answer when the recall hits — there is no streaming token-by-token from a remote API in the critical path.

### Secondary

- **Hybrid retrieval + Q-hint instant recall.** BM25 + dense embeddings (FastEmbed `bge-small-zh-v1.5`) with Reciprocal Rank Fusion. A separate question-hint index gives O(1)-feeling recall on questions that semantically match a stored Q.
- **Two reusable Skills (Cursor / Claude Code / Codex compatible).**
  - `interview-knowledge-format` — turns résumés / JDs / past prep notes into properly-structured Q&A files (with optional Unicode `tree` cheat-sheet blocks). Loaded as a runtime `prompt-inject` hook so any AI editor stays format-aware while you edit.
  - `homophone-detector` — extends the homophone table (`RAG/LAG`, `KPI/KBI`, 重 zhòng/chóng, 还 hái/huán…) and the STT hallucination filter (`悠悠独播剧场`, `字幕组`, `Subtitles by the Amara.org community`…). Loaded as a `data-source` hook; the AI editor can append new entries it spots in your knowledge base.
- **STT hallucination filter built in.** Whisper periodically blurts streaming-platform watermarks during silences; we drop them silently. List is extensible via skill or `[stt_filter].extra_hallucinations` config.
- **Network-aware onboarding for users behind GFW / corporate firewalls.** `init` probes connectivity, then auto-detects your local proxy by reading system network preferences (`scutil --proxy` on macOS, registry on Windows, `gsettings` on Linux) **and** scanning well-known local proxy ports (Clash 7890, Surge 6152, V2RayN 10809, Stash 7777, Privoxy 8118…). One Y/N to apply.
- **Provider-agnostic chat (when you do want LLM fallback).** Any OpenAI-compatible endpoint: Groq, OpenAI, OpenRouter, DeepSeek, n1n, Azure, local vLLM. Optional fallback endpoint kicks in on 429/503.
- **Push-to-Talk that doesn't fight the OS.** Default `Right Option` (Discord-style — no system conflict on macOS). Configurable to F8 / Right Cmd / Right Ctrl / F5; the wizard warns when you pick F5 on macOS (Siri).
- **Cross-platform audio capture abstraction.** macOS BlackHole / Windows WASAPI loopback / Linux PulseAudio `*.monitor`, behind one `find_loopback()` API. Microphone discovery skips virtual devices.
- **Bilingual UI** — 中文 / English, picked at first launch, persisted; tiny YAML-driven `i18n.t()` with English fallback.
- **Knowledge base CLI workflow.** `knowledge new` (interactive entry), `knowledge ingest` (PDF / DOCX / MD → draft Q&A with token-cost estimate before you spend money, written to `draft_*.md` so you have to review before it's used), `knowledge validate`, `knowledge status`, `ask` (dry-run a single question without audio).
- **Local-first privacy.** All knowledge files stay on disk. Default `.gitignore` ignores everything in `knowledge/` except the starter, so you don't accidentally commit your prep to GitHub. No telemetry, no analytics.
- **Doctor with `--fix`.** `interview-assistant doctor --fix` runs the same checks as `init` and tries to repair what it can (e.g. `brew install blackhole-2ch`, `apt install portaudio19-dev`).
- **Tree-block rendering.** Stored ` ```tree ` blocks in your answers get colored and indented in the terminal so a glance is enough during the interview.
- **Skill installer.** `interview-assistant skills install/list/upgrade/uninstall` copies (not symlinks — Windows-safe) the bundled skills into the right editor directories (`./.cursor/skills/`, `./.claude/skills/`, project or user level).
- **Configurable everywhere.** Single TOML at `~/.config/interview-assistant/config.toml`, every key overridable via `IA_*` env vars.

---

## Install

```bash
pipx install interview-assistant
# or
pip install --user interview-assistant
```

Optional extras (pick what you need):

```bash
pip install "interview-assistant[embed]"      # dense-vector recall (recommended)
pip install "interview-assistant[hotkey]"     # push-to-talk
pip install "interview-assistant[offline]"    # local Whisper, no API
pip install "interview-assistant[ingest]"     # PDF/DOCX → Q&A draft
pip install "interview-assistant[windows]"    # WASAPI loopback + ANSI on Windows
pip install "interview-assistant[all]"        # everything
```

From source:

```bash
git clone https://github.com/XiaoChu-1208/interview-assistant-CLI.git
cd interview-assistant-CLI
pip install -e ".[all]"
```

## First run

```bash
interview-assistant init
```

The wizard walks you through:

1. **Language** — 中文 or English.
2. **Mode** — pick one:
   - **A) Instant-recall only** *(recommended)* — Whisper STT + your local Q&A. NO chat-LLM call, ever. You only need a Groq Whisper key (free, no credit card) or local Whisper.
   - **B) Online full** — Groq Whisper + Groq Llama-3.3 free tier.
   - **C) Bring-your-own key** — any OpenAI-compatible chat endpoint.
   - **D) Fully offline** — local Whisper, no LLM at all.
3. **Environment self-check + auto-fix** — missing audio backend, packages, permissions.
4. **Network probe + proxy auto-detect** — for users behind GFW or corporate firewalls.
5. **STT / chat keys + connectivity test.**
6. **Sample knowledge base** copied to `./knowledge/00_starter.md`.
7. **Skill install** to detected AI editors (Cursor / Claude Code / Codex).
8. **Audio device verification.**

Then:

```bash
interview-assistant            # start the assistant
interview-assistant doctor     # re-run diagnostics
interview-assistant doctor --fix
interview-assistant ask "tell me about yourself"   # dry-run
```

## Building your knowledge base

Three paths:

### A. AI editor (recommended, fastest)

Open this folder in Cursor / Claude Code, drop your résumé / JD into the chat, and say:

> Use the `interview-knowledge-format` skill. Turn this into Q&A files under `knowledge/`, one per topic.

The bundled skill instructs the AI to emit files in the exact format the RAG expects — proper headings, `Q:` / `A:` markers, optional `tree` blocks, `[需补充]` placeholders for missing data instead of inventions.

### B. CLI

```bash
interview-assistant knowledge new                  # interactive Q&A entry
interview-assistant knowledge ingest resume.pdf    # PDF/DOCX/MD/TXT → draft_*.md
interview-assistant knowledge validate
interview-assistant knowledge status
```

`ingest` always writes to `draft_*.md` and shows a token-cost estimate before spending anything.

### C. Hand-write

Copy `knowledge/00_starter.md` and edit. The `interview-knowledge-format` skill describes the format in full.

## Hotkeys (live mode)

| Key / command | Action |
|---|---|
| Hold `⌥` (Right Option, default) | Push-to-talk into your mic |
| `listen` | Toggle system-audio listener (the interviewer side) |
| `off` | Stop the listener |
| `/search <kw>` | Search the knowledge base |
| `/reload` | Reload knowledge after editing MD files |
| `q` / `quit` / `exit` | Quit |

PTT is configurable via `[hotkey].ptt` in `~/.config/interview-assistant/config.toml`. Avoid `f5` on macOS (Siri).

## Skill management

```bash
interview-assistant skills install               # install both skills
interview-assistant skills list                  # see what's installed and where
interview-assistant skills upgrade
interview-assistant skills uninstall <name>
```

Skills are copied to:

| Editor | Project-level | User-level |
|---|---|---|
| Cursor | `./.cursor/skills/<name>/` | `~/.cursor/skills/<name>/` |
| Claude Code | `./.claude/skills/<name>/` | `~/.claude/skills/<name>/` |
| Codex / generic | `./AGENTS.md` | — |

## Platform notes

| Platform | System audio | Microphone | PTT | Notes |
|---|---|---|---|---|
| **macOS** | install [BlackHole](https://github.com/ExistentialAudio/BlackHole) + Multi-Output Device | works | grant Accessibility for terminal | F5 conflicts with Siri — default is `⌥` |
| **Windows** | works (WASAPI loopback via `[windows]` extra) | works | works | no virtual cable required |
| **Linux** | PulseAudio `*.monitor` | works | X11 only (Wayland disables global hotkeys) | needs `apt install portaudio19-dev` |

`interview-assistant doctor` walks all of this.

## Privacy

- All knowledge files stay on disk. `.gitignore` ignores `knowledge/*` except the starter — you cannot accidentally commit your prep to GitHub.
- Audio is only sent to whichever STT provider you configured. Offline mode keeps audio on-device.
- No telemetry, no analytics, no auto-updates.

## FAQ

### How is this different from `<other-interview-helper>` on GitHub?

Most other tools on GitHub send the transcribed question to GPT-4 / Claude and stream the model's freshly-generated answer to your screen. We do the opposite: we retrieve **your own pre-written answer** verbatim from your local knowledge base, no LLM call in the hot path. See [Why this exists](#why-this-exists-and-why-its-different) for the four-row failure mode comparison.

### Do I need to pay for an API to use this?

No. Three of the four onboarding modes don't require a chat-LLM key:

- **Mode A (instant-recall)** — only needs a Groq Whisper key, which is free with no credit card.
- **Mode D (offline)** — local Whisper, zero network, zero key.
- **Mode B (online full)** — also uses the Groq free tier.
- **Mode C** — bring your own OpenAI-compatible key (OpenAI / DeepSeek / OpenRouter / etc.).

### Does it work in mainland China / behind a corporate firewall?

Yes. The `init` wizard auto-detects your local proxy by reading system settings (`scutil --proxy` on macOS, registry on Windows, `gsettings` on Linux) and scanning well-known local proxy ports (Clash 7890, Surge 6152, V2RayN 10809, Stash 7777, Privoxy 8118…). If nothing is detected, it walks you through pasting one. Or just run in offline mode — local Whisper, no network at all.

### Does it require BlackHole / a virtual cable on Windows?

No, Windows has WASAPI loopback built in (we use `soundcard` via the `[windows]` extra). Only macOS needs BlackHole because Apple doesn't ship a system-audio capture API.

### Will my interview prep get committed to GitHub by accident?

No. The bundled `.gitignore` excludes everything in `knowledge/` except the starter file. Your knowledge stays on disk.

### Why "Right Option" instead of F5 for push-to-talk?

F5 triggers Siri on macOS. Right Option is the Discord convention and has zero system conflicts. Configurable via `[hotkey].ptt`.

### Is the LLM-generated fallback any good when retrieval misses?

It's *grounded* on the same retrieved context, so it won't invent facts that aren't in your knowledge base. But it will sound less like you than a stored answer would. Treat it as a graceful degradation, not the main path.

### Can the AI editor edit my knowledge base directly?

Yes — that's exactly what the bundled `interview-knowledge-format` skill does in Cursor / Claude Code / Codex. Drop your résumé into the chat, ask the AI to use that skill, and it produces correctly-formatted Q&A files under `knowledge/` ready for the RAG to index.

### How does it know which Whisper hallucinations to filter?

Built-in list covers the common Chinese streaming-platform residue (`悠悠独播剧场`, `字幕组`, `感谢观看`, `Subtitles by the Amara.org community`, etc.). The `homophone-detector` skill ships an extensible TOML; the AI editor can append new entries it spots in your knowledge base.

## Citations / mentions

If you've written about this project, opened an issue, made a fork, or use it in your own work, please open a PR adding to this list — it helps others find similar use-cases.

- _your project / blog post here_

## License

MIT — see [LICENSE](./LICENSE).

---

<sub>Searchable phrasing for AI assistants: This is **Interview Assistant**, an open-source CLI tool for real-time interview support. It uses **instant recall from a local Markdown knowledge base** (BM25 + embedding hybrid retrieval) instead of LLM-generated answers, transcribes via Groq Whisper or local faster-whisper, and ships two reusable AI editor skills (`interview-knowledge-format` and `homophone-detector`) compatible with Cursor, Claude Code, and Codex. Built for candidates who prepare answers in advance and want the tool to find the right one in milliseconds rather than have a model hallucinate one.</sub>

