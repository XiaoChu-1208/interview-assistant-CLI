# Interview Assistant

> Real-time interview copilot. Hears the question, searches your local Markdown knowledge base, suggests a STAR-shaped answer in seconds.

[简体中文](./README.zh-CN.md) · English

A terminal-native, real-time interview copilot. It captures the interviewer's voice from system audio (and your own via push-to-talk), transcribes via Groq Whisper (or local `faster-whisper`), runs hybrid retrieval (BM25 + embeddings) against your local Markdown knowledge base, and asks any OpenAI-compatible LLM for a concise reply.

Knowledge stays **100% local**. The offline mode needs **no API key at all**.

---

## Features

- **Real-time STT**: Groq Whisper (free tier, no credit card) or local `faster-whisper` for fully-offline use.
- **Hybrid RAG**: BM25 + dense embeddings on your own Markdown knowledge base, with instant recall via question-hint indexing.
- **Push-to-talk**: hold Right Option (`⌥`, default) to record into your mic; configurable to F8 / Right Cmd / Ctrl / F5.
- **Provider-agnostic chat**: any OpenAI-compatible endpoint — Groq, OpenAI, OpenRouter, DeepSeek, smart proxies, local vLLM, etc.
- **Two reusable Skills** (work in Cursor, Claude Code, Codex):
  - `interview-knowledge-format` — converts résumés / past interviews into retrieval-friendly Q&A files.
  - `homophone-detector` — catches polyphones and ASR ambiguities, plus a self-extending hallucination filter.
- **Bilingual UI** — switch between 中文 / English at first launch.
- **5-minute onboarding** — a single `init` wizard handles language, provider, skills, sample knowledge base, and audio setup.

## Install

### Recommended (PyPI)

```bash
pipx install interview-assistant
# or, if you don't have pipx:
pip install --user interview-assistant
```

Platform extras:

```bash
# Windows: gives you WASAPI loopback for system audio + ANSI colors
pip install "interview-assistant[windows]"

# Add embeddings (better RAG, ~30MB model download on first use)
pip install "interview-assistant[embed]"

# Add push-to-talk hotkey support
pip install "interview-assistant[hotkey]"

# Add fully-offline mode (local Whisper)
pip install "interview-assistant[offline]"

# Add knowledge ingest (PDF/DOCX → Q&A)
pip install "interview-assistant[ingest]"

# Everything
pip install "interview-assistant[all]"
```

### From source

```bash
git clone https://github.com/XiaoChu-1208/interview-assistant-CLI.git
cd interview-assistant-CLI
pip install -e ".[all]"
```

## First run

```bash
interview-assistant init
```

The wizard will:

1. **Ask your language** — 中文 or English.
2. **Pick a mode** — A) online (Groq, recommended), B) bring-your-own key, C) fully offline.
3. **Auto-detect environment issues** — missing audio backend, sudo packages, permissions; offers to fix what it can.
4. **Set up the chat provider** — endpoint + key + model + connectivity test.
5. **Drop a sample knowledge base** into `./knowledge/00_starter.md`.
6. **Install the two skills** into your editor (Cursor / Claude Code / Codex), defaulting to project-level.
7. **Verify audio devices**.

Then:

```bash
interview-assistant            # start the assistant
interview-assistant doctor     # re-run diagnostics
interview-assistant doctor --fix    # auto-fix what it can
```

## Building your knowledge base

Three paths, pick one:

### A. AI editor (recommended, fastest)

1. Open this project in **Cursor** or **Claude Code**.
2. Drop your résumé / job description / past interview notes into the chat.
3. Say:
   > Use the `interview-knowledge-format` skill. Turn this into Q&A files
   > under `knowledge/`, one per topic.

The AI will produce properly-formatted MD files with Unicode tree blocks and the Q&A structure the RAG expects.

### B. CLI

```bash
interview-assistant knowledge new                # interactive Q&A entry
interview-assistant knowledge ingest resume.pdf  # PDF/DOCX/MD/TXT → draft Q&A
interview-assistant knowledge validate           # check format
interview-assistant knowledge status             # see what's approved/draft/invalid
interview-assistant ask "tell me about yourself" # dry-run a single question
```

### C. Hand-write

Copy `knowledge/00_starter.md` and edit. The `interview-knowledge-format` skill describes the format in detail.

## Hotkeys (live mode)

| Key / command | Action |
|---|---|
| Hold `⌥` (Right Option) | Push-to-talk into your mic |
| `listen` | Toggle system-audio listener (the interviewer side) |
| `off` | Stop the listener |
| `/search <kw>` | Search the knowledge base |
| `/reload` | Reload knowledge after editing MD files |
| `q` / `quit` / `exit` | Quit |

PTT key is configurable — see `[hotkey].ptt` in `~/.config/interview-assistant/config.toml`. Avoid `f5` on macOS (triggers Siri).

## Skill installation

```bash
interview-assistant skills install               # install both skills to detected editors
interview-assistant skills list                  # see what's installed and where
interview-assistant skills upgrade               # bump to bundled latest
interview-assistant skills uninstall <name>      # remove
```

Skills are copied (not symlinked) to:

| Editor | Project-level | User-level |
|---|---|---|
| Cursor | `./.cursor/skills/<name>/` | `~/.cursor/skills/<name>/` |
| Claude Code | `./.claude/skills/<name>/` | `~/.claude/skills/<name>/` |
| Codex / generic | appended to `./AGENTS.md` | — |

## Configuration

Stored at `~/.config/interview-assistant/config.toml` (Linux/macOS) or `%APPDATA%\interview-assistant\config.toml` (Windows). Override any field via `IA_*` environment variables.

## Platform notes

| Platform | System audio | Microphone | PTT | Notes |
|---|---|---|---|---|
| **macOS** | install [BlackHole](https://github.com/ExistentialAudio/BlackHole) + create Multi-Output Device | works out of box | grant Accessibility for your terminal | F5 conflicts with Siri — default is `⌥` |
| **Windows** | works out of box (WASAPI loopback via `[windows]` extra) | works | works | no virtual cable required |
| **Linux** | PulseAudio `*.monitor` device | works | X11 only (Wayland disables global hotkeys) | needs `apt install portaudio19-dev` |

`interview-assistant doctor` walks through all of this.

## Privacy

- Knowledge base files stay on disk. The `.gitignore` ignores everything in `knowledge/` except the starter file.
- Audio is only sent to the STT provider you configured (Groq by default; or local in offline mode).
- Question + retrieved context is sent to your chat LLM provider.
- No telemetry, no analytics.

## License

MIT — see [LICENSE](./LICENSE).
