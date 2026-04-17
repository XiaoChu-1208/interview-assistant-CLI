"""Question handling: distill → search → instant-recall or LLM stream."""
from __future__ import annotations

from typing import Any

from . import i18n, providers, rag
from .theme import B, BCYN, BGRN, BRED, BYEL, DIM, RST, WARM, BBLU, tree_colors


SYSTEM_PROMPT_BASE = """你是用户的专属面试助手。

你的任务：根据用户提供的面试文档，给出精准的回答建议。这是面试中的快速小抄，必须一眼抓到重点，拒绝废话。

## 输出格式

- 用 1. 2. 3. 分点，每点一段，点之间空行。
- 加粗只用在**关键数据**和**核心结论**上，每段最多加粗 1-2 处，不要滥用。
- 经历类问题用 STAR：背景 → 行动 → 结果（带数据），不需要写出 S/T/A/R 标签。
- 禁止大段落，每段不超过 2 行。

## 回答规则

1. 如果文档中有极度匹配的现成回答，直接输出原文，不改写。
2. 结论前置：第一句就是核心结论。
3. 只说文档里有的内容，不要自由发挥添加文档中没有的信息。
4. 直接以用户的第一人称输出面试回答本身。禁止出现任何元叙述，如"你可以这样回答"、"如果面试官想听"、"我可以先概括"、"建议从…角度"。输出的每一句话都必须是面试者对面试官说的原话。
5. 长度：5-8 句话，够用就停。不要输出总结段、不要问"还需要什么"。
6. 默认中文回答（若用户文档为英文则用英文）。
7. 文档无相关内容时，说「文档中没有直接相关的内容」，再给简短通用思路。严禁编造。
"""

INSTANT_RECALL_SCORE_THRESHOLD = 15.0
INSTANT_RECALL_QHINT_SIM_MIN = 0.55


def build_system_prompt(extra_injections: list[str]) -> str:
    """Compose the full system prompt with skill-provided additions."""
    parts = [SYSTEM_PROMPT_BASE]
    for inject in extra_injections:
        if inject:
            parts.append("\n## Extra context (from installed skill)\n\n" + inject.strip())
    return "\n".join(parts)


def _build_context(results, total_budget=6000):
    out, used = [], 0
    for score, sec in results:
        chunk = f"## {sec['title']}\n\n{sec['content']}\n"
        if used + len(chunk) > total_budget:
            break
        out.append(chunk)
        used += len(chunk)
    return "\n".join(out)


def render_tree(tree_text: str) -> str:
    """Colorize a stored Unicode tree block for the terminal."""
    colors = tree_colors()
    out = []
    for line in tree_text.splitlines():
        if line.strip().startswith("▶"):
            out.append(colors["root"] + line + RST)
        elif any(c in line for c in "①②③④⑤⑥⑦⑧⑨"):
            out.append(colors["step"] + line + RST)
        elif line.strip().startswith("└"):
            out.append(colors["leaf"] + line + RST)
        elif line.lstrip().startswith(("├", "└", "│")):
            out.append(colors["line"] + line + RST)
        else:
            out.append(colors["branch"] + line + RST)
    return "\n".join(out)


def chat_enabled(cfg: dict) -> bool:
    """`chat.enabled` defaults to True if an api_key exists; explicit False wins."""
    chat = cfg.get("chat", {}) or {}
    if chat.get("enabled") is False:
        return False
    return bool(chat.get("api_key"))


def _print_recall_hit(sec: dict) -> str:
    print(f"\n{BGRN}{B}  {sec['title']}{RST}")
    if sec.get("tree_text"):
        print(render_tree(sec["tree_text"]))
    if sec.get("answer_text"):
        for line in sec["answer_text"].splitlines():
            print(f"  {line}")
    print()
    return sec.get("answer_text", "")


def _print_retrieval_only(results: list, top_k: int = 3) -> str:
    """No-LLM fallback: dump the top-k retrieved sections themselves."""
    if not results:
        print(f"  {DIM}{i18n.t('run.no_relevant_doc')}{RST}\n")
        return ""
    print()
    parts: list[str] = []
    for i, (score, sec) in enumerate(results[:top_k], 1):
        print(f"  {BGRN}{B}{i}. {sec['title']}{RST}  {DIM}(score {score:.2f}){RST}")
        if sec.get("tree_text"):
            print(render_tree(sec["tree_text"]))
        if sec.get("answer_text"):
            for line in sec["answer_text"].splitlines():
                print(f"  {line}")
        else:
            for line in sec["content"].splitlines()[:8]:
                print(f"  {line}")
        print()
        parts.append(sec.get("answer_text") or sec["content"])
    return "\n\n---\n\n".join(parts)


def handle_question(
    query: str,
    sections: list[dict],
    bm25_index: dict,
    cfg: dict,
    *,
    embedder=None,
    doc_embeddings=None,
    qhint_sections=None,
    qhint_embeddings=None,
    chat_history: list | None = None,
    system_prompt: str = SYSTEM_PROMPT_BASE,
) -> tuple[str, str]:
    """Answer a single question. Returns (used_query, full_answer_text).

    Three execution paths:
      1. Instant recall hit  → print stored answer (LLM never touched).
      2. chat disabled        → print top-3 retrieved sections (retrieval-only).
      3. chat enabled         → stream LLM grounded on retrieved context.
    """
    if not sections:
        print(f"  {DIM}{i18n.t('run.no_relevant_doc')}{RST}\n")
        return query, ""

    instant = rag.instant_recall(
        query, qhint_sections or [], qhint_embeddings,
        embedder, sim_min=INSTANT_RECALL_QHINT_SIM_MIN,
    ) if qhint_sections else None

    results = rag.search_documents(query, sections, bm25_index, embedder, doc_embeddings, top_k=6)

    use_llm = chat_enabled(cfg)
    # In retrieval-only mode (no LLM), be a bit more generous about what
    # counts as a recall hit — there's no other path to a useful answer.
    score_floor = INSTANT_RECALL_SCORE_THRESHOLD if use_llm else INSTANT_RECALL_SCORE_THRESHOLD * 0.5
    if (
        instant
        and instant[0] >= INSTANT_RECALL_QHINT_SIM_MIN
        and results
        and results[0][0] >= score_floor
    ):
        return query, _print_recall_hit(instant[1])

    if not use_llm:
        return query, _print_retrieval_only(results, top_k=3)

    if not results:
        print(f"  {DIM}{i18n.t('run.no_relevant_doc')}{RST}\n")
        return query, ""

    context = _build_context(results)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"参考材料：\n\n{context}\n\n面试官问：{query}"},
    ]
    if chat_history:
        history_msgs = []
        for h in chat_history[-3:]:
            history_msgs.append({"role": "user", "content": h["q"]})
            history_msgs.append({"role": "assistant", "content": h["a"][:500]})
        messages = [messages[0]] + history_msgs + [messages[1]]

    full_text = []
    print()
    try:
        for delta in providers.chat(cfg["chat"], messages, stream=True, max_tokens=2000):
            print(delta, end="", flush=True)
            full_text.append(delta)
        print("\n")
    except Exception as e:
        print(f"\n{BRED}  llm error: {e}{RST}\n")
        # Final degraded mode: print top retrieved sections as plain fallback.
        return query, _print_retrieval_only(results, top_k=3)

    return query, "".join(full_text)
