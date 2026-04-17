---
name: interview-knowledge-format
version: "1.0"
description: |
  Convert résumé / job descriptions / past interview notes into Markdown Q&A
  files in the format Interview Assistant's RAG expects (sections + Q/A pairs +
  optional Unicode tree blocks). Use when the user wants to populate `knowledge/`
  for the first time, ingest a new role, or refactor messy notes.
trigger_words:
  - 知识库
  - knowledge base
  - Q&A
  - 整理简历
  - 整理面试
  - resume
  - interview prep
runtime:
  hook: prompt-inject
---

# interview-knowledge-format

A Skill for both AI editors (Cursor / Claude Code / Codex) **and** the
Interview Assistant runtime. The runtime injects the format spec below into
the chat system prompt so the LLM stays aligned even mid-session.

<!-- INJECT-START -->

When you generate or edit knowledge-base content, follow this exact format.

## File rules

1. One topic per file. Filename = lowercase-snake, e.g. `about_me.md`,
   `pm_methodology.md`, `data_analytics.md`. Drafts use prefix `draft_`.
2. UTF-8, LF line endings. No BOM.
3. Top of file: `# <Topic>` (H1) + a one-line tagline if helpful.

## Section rules

Each retrievable unit MUST start with `## ` (H2). The H2 title IS the
question. Multi-question files are encouraged.

```
## How do you handle conflict on a cross-functional team?

**Q:** How do you handle conflict on a cross-functional team?

**A:**

<concise STAR answer in the user's first person, 4-8 sentences>

> Bullet 1: opening line you'd actually say out loud
> Bullet 2: concrete data point
> Bullet 3: result with metric
```

## Optional Unicode tree

If the user wants a visual cheat-sheet rendered in the terminal, append a
fenced `tree` block at the END of the section:

````
```tree
▶ Conflict resolution
├─ ① ack the friction
├─ ② re-anchor to user metric
└─ ③ propose an A/B test
```
````

The runtime renders this with color. Keep ≤ 6 lines, ≤ 60 chars per line.

## Hallucination guard

- Quote sources verbatim where possible.
- If source data is missing, write `[需补充]` (Chinese) or `[TBD]` (English) —
  never invent numbers.
- Never substitute company names or metrics.

<!-- INJECT-END -->

## How to use this skill

### From an AI editor

> "Use the `interview-knowledge-format` skill. Convert my résumé into one
> Q&A file per role under `knowledge/`."

The AI will:
1. Read the source.
2. Group into topics.
3. Emit one MD file per topic in the format above.
4. Mark each with `draft_` prefix until you review.

### From the runtime

The Interview Assistant auto-loads this skill at startup; the spec above is
appended to the LLM system prompt so all generated answers stay format-aware.

## Templates

See `templates/example-qa.md` for a full filled-in example.
