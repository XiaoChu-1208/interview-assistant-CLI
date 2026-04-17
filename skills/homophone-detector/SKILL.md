---
name: homophone-detector
version: "1.0"
description: |
  Detect polyphones, near-homophones, and ASR ambiguities. Two roles: (1) at
  runtime, extends the homophone table and the STT hallucination filter so the
  assistant doesn't get confused by "RAG vs LAG" or by streaming-platform
  watermark phrases; (2) in AI editors, gives the LLM a checklist for spotting
  ambiguities in user-generated knowledge bases.
trigger_words:
  - 多音字
  - homophone
  - 谐音
  - 误识别
  - hallucination
  - filter
runtime:
  hook: data-source
  data: data/homophones.toml
  target: homophones
---

# homophone-detector

A two-faced skill:

* **Runtime**: extends `interview_assistant.homophones.PHONETIC_GROUPS` from
  `data/homophones.toml`, and contributes a hallucination-filter list from
  `data/hallucinations.toml` (loaded as a separate `runtime:` hook by the
  assistant's loader — see below).
* **AI editor**: a checklist for the model to scan a knowledge base and flag
  potentially-confusable terms.

## Runtime contract

This skill ships TWO data files. The loader treats each as a separate
`runtime` block via `data-source`:

* `data/homophones.toml` → merged into `PHONETIC_GROUPS`
* `data/hallucinations.toml` → appended to `STTFilter.hallucinations`

`SKILL.md` only declares the first hook in frontmatter; the loader also scans
the directory for any `*.toml` and applies them by `target` field inside
the file. (See `data/hallucinations.toml`.)

## For AI editors

When the user says "scan my knowledge base for ambiguities" or you're editing
their `knowledge/` folder:

1. List every English/Chinese term that has a known confusable partner. Flag
   pairs like `(RAG, LAG)`, `(KPI, KBI)`, `(ROI, RAI/RAW)`, polyphone words
   in Chinese (重 zhòng/chóng, 还 hái/huán, 长 cháng/zhǎng, 行 xíng/háng).
2. For each flag, propose ONE of:
   - Add the canonical form to `data/homophones.toml`.
   - Add a clarifying parenthetical in the knowledge file itself, e.g.
     "RAG（Retrieval-Augmented Generation）".
3. Never silently rewrite the user's content — present diffs and ask.

## Adding entries

Format of `homophones.toml`:

```toml
[[entry]]
canonical = "rag"
variants  = ["lag", "rad", "rack", "raq"]
note      = "Retrieval-Augmented Generation"

[[entry]]
canonical = "重"
variants  = []
polyphone = ["zhòng", "chóng"]
example   = "重要 zhòng / 重新 chóng"
```

Format of `hallucinations.toml`:

```toml
target = "hallucinations"

[[entry]]
text = "悠悠独播剧场"
source = "Whisper streaming-platform residue"

[[entry]]
text = "感谢观看"
source = "Whisper YouTube outro residue"
```
