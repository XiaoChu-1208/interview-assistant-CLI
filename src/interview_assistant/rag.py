"""Hybrid RAG: BM25 + dense embeddings + RRF, plus instant Q-hint recall.

This is a focused port of the original interview_assistant.py logic, with
hard-coded paths replaced by configurable knowledge dirs.
"""
from __future__ import annotations

import hashlib
import os
import re
from collections import Counter
from math import log
from pathlib import Path
from typing import Any

import numpy as np

from . import config as _cfg


_Q_PAT = re.compile(r"^\*{0,2}[Qq问题]{1,2}[：:.]\s*")


def _extract_tree_block(text: str) -> tuple[str, str]:
    """Return (tree_text, text_without_tree)."""
    m = re.search(r"```tree\n(.*?)```", text, re.DOTALL)
    if not m:
        return "", text
    return m.group(1), text[:m.start()] + text[m.end():]


def _is_metadata_only(text: str) -> bool:
    stripped = re.sub(r"```tree.*?```", "", text, flags=re.DOTALL).strip()
    if len(stripped) < 30:
        return True
    if stripped.count("|") > stripped.count("\n") * 2:
        return True
    return False


def load_documents(dirs: list[str]) -> list[dict]:
    """Load all .md files from the configured knowledge directories."""
    sections: list[dict] = []
    for d in dirs:
        path = Path(os.path.expanduser(d)).resolve()
        if not path.is_dir():
            continue
        md_files = sorted(p for p in path.glob("*.md") if not p.name.startswith("draft_"))
        for fpath in md_files:
            with open(fpath, "r", encoding="utf-8") as f:
                raw = f.read()
            blocks = re.split(r"\n(?=#{1,4} )", raw)
            for block in blocks:
                lines = block.strip().split("\n")
                if not lines:
                    continue
                title_line = lines[0].lstrip("#").strip()
                block_title = f"{fpath.name} > {title_line}" if title_line else fpath.name
                qa_chunks: list[tuple[str, str]] = []
                current_q = ""
                current_lines: list[str] = []
                in_qa = False
                for line in lines[1:]:
                    if _Q_PAT.match(line):
                        if current_lines:
                            qa_chunks.append((current_q, "\n".join(current_lines).strip()))
                        current_q = _Q_PAT.sub("", line).strip().rstrip("*")
                        current_lines = [line]
                        in_qa = True
                    else:
                        current_lines.append(line)
                if current_lines:
                    qa_chunks.append((current_q, "\n".join(current_lines).strip()))

                if in_qa and qa_chunks:
                    for q_text, content in qa_chunks:
                        if len(content) < 15:
                            continue
                        sub_title = f"{block_title} > {q_text[:50]}" if q_text else block_title
                        cl = content.split("\n")
                        ans_text = "\n".join(cl[1:]).strip() if len(cl) > 1 else ""
                        tree, ans_clean = _extract_tree_block(ans_text)
                        if _is_metadata_only(ans_clean):
                            ans_clean = ""
                        sec = {
                            "file": fpath.name, "title": sub_title, "content": content,
                            "q_hint": q_text.lower(), "answer_text": ans_clean,
                        }
                        if tree:
                            sec["tree_text"] = tree
                        sections.append(sec)
                else:
                    if len(block.strip()) < 15:
                        continue
                    bl = block.strip().split("\n")
                    ans = "\n".join(bl[1:]).strip() if len(bl) > 1 else ""
                    tree, ans_clean = _extract_tree_block(ans)
                    if _is_metadata_only(ans_clean):
                        ans_clean = ""
                    sec = {
                        "file": fpath.name, "title": block_title, "content": block.strip(),
                        "q_hint": title_line.lower(), "answer_text": ans_clean,
                    }
                    if tree:
                        sec["tree_text"] = tree
                    sections.append(sec)
    for i, sec in enumerate(sections):
        sec["idx"] = i
    return sections


# ─────────────────────────── BM25 ──────────────────────────

def tokenize(text: str) -> list[str]:
    text = text.lower()
    en = re.findall(r"[a-z][a-z0-9]+", text)
    zh = re.findall(r"[\u4e00-\u9fff]", text)
    return en + zh


def build_bm25_index(sections: list[dict]) -> dict:
    df: Counter = Counter()
    docs: list[list[str]] = []
    for sec in sections:
        toks = tokenize(sec["content"])
        docs.append(toks)
        for tok in set(toks):
            df[tok] += 1
    n = len(docs)
    idf = {tok: log((n - cnt + 0.5) / (cnt + 0.5) + 1) for tok, cnt in df.items()}
    avg_len = sum(len(d) for d in docs) / max(n, 1)
    for sec, toks in zip(sections, docs):
        sec["_tokens"] = toks
        sec["_tf"] = Counter(toks)
    return {"idf": idf, "avg_len": avg_len}


def bm25_score(query_tokens, section, idf, k1=1.5, b=0.75, avg_len=500.0):
    score = 0.0
    doc_len = len(section["_tokens"])
    tf = section["_tf"]
    for tok in query_tokens:
        if tok not in tf or tok not in idf:
            continue
        f = tf[tok]
        score += idf[tok] * (f * (k1 + 1)) / (f + k1 * (1 - b + b * doc_len / avg_len))
    return score


def bm25_search(query: str, sections, index, top_k=12):
    qtoks = tokenize(query)
    scored = []
    for sec in sections:
        s = bm25_score(qtoks, sec, index["idf"], avg_len=index["avg_len"])
        if s > 0:
            scored.append((s, sec))
    scored.sort(key=lambda x: -x[0])
    return scored[:top_k]


# ─────────────────────────── embeddings ──────────────────────

EMBED_MODEL = "BAAI/bge-small-zh-v1.5"


def init_embedder():
    """Lazy import; returns None if fastembed isn't installed."""
    try:
        from fastembed import TextEmbedding
    except ImportError:
        return None
    cache = _cfg.cache_dir() / "models"
    return TextEmbedding(EMBED_MODEL, cache_dir=str(cache))


def _md_fingerprint(sections) -> str:
    content = "|".join(s["title"] + s["content"] for s in sections)
    return hashlib.md5(content.encode()).hexdigest()


def get_or_build_embeddings(sections, embedder) -> np.ndarray | None:
    if embedder is None:
        return None
    cache_file = _cfg.cache_dir() / "embeddings.npz"
    fp = _md_fingerprint(sections)
    if cache_file.exists():
        try:
            data = np.load(cache_file, allow_pickle=False)
            if str(data["fp"]) == fp and data["embs"].shape[0] == len(sections):
                return data["embs"]
        except Exception:
            pass
    texts = [s["content"][:1500] for s in sections]
    embs = np.array(list(embedder.embed(texts)))
    try:
        np.savez(cache_file, fp=np.array(fp), embs=embs)
    except Exception:
        pass
    return embs


def vec_search(query, sections, embedder, doc_embeddings, top_k=12):
    if embedder is None or doc_embeddings is None:
        return []
    q_emb = next(iter(embedder.embed([query])))
    q_norm = q_emb / (np.linalg.norm(q_emb) + 1e-9)
    d_norm = doc_embeddings / (np.linalg.norm(doc_embeddings, axis=1, keepdims=True) + 1e-9)
    sims = d_norm @ q_norm
    idx = np.argsort(-sims)[:top_k]
    return [(float(sims[i]), sections[i]) for i in idx if sims[i] > 0]


def _rrf_merge(bm25_results, vec_results, k=60):
    scores: dict[int, float] = {}
    sec_map: dict[int, dict] = {}
    for rank, (_, sec) in enumerate(bm25_results):
        scores[sec["idx"]] = scores.get(sec["idx"], 0) + 1 / (k + rank)
        sec_map[sec["idx"]] = sec
    for rank, (_, sec) in enumerate(vec_results):
        scores[sec["idx"]] = scores.get(sec["idx"], 0) + 1 / (k + rank)
        sec_map[sec["idx"]] = sec
    merged = sorted(scores.items(), key=lambda x: -x[1])
    return [(s, sec_map[i]) for i, s in merged]


def search_documents(query, sections, index, embedder=None, doc_embeddings=None, top_k=6):
    bm25 = bm25_search(query, sections, index, top_k=12)
    vec = vec_search(query, sections, embedder, doc_embeddings, top_k=12)
    if not vec:
        return bm25[:top_k]
    return _rrf_merge(bm25, vec)[:top_k]


# ─────────────────────────── instant Q-hint recall ──────────

def build_qhint_index(sections, embedder=None):
    qhint_secs = [s for s in sections if s.get("q_hint")]
    if embedder is None or not qhint_secs:
        return qhint_secs, None
    texts = [s["q_hint"] for s in qhint_secs]
    embs = np.array(list(embedder.embed(texts)))
    return qhint_secs, embs


def instant_recall(query, qhint_secs, qhint_embs, embedder=None, sim_min=0.55):
    if not qhint_secs or qhint_embs is None or embedder is None:
        return None
    q_emb = next(iter(embedder.embed([query])))
    q_norm = q_emb / (np.linalg.norm(q_emb) + 1e-9)
    d_norm = qhint_embs / (np.linalg.norm(qhint_embs, axis=1, keepdims=True) + 1e-9)
    sims = d_norm @ q_norm
    best = int(np.argmax(sims))
    if sims[best] >= sim_min:
        return float(sims[best]), qhint_secs[best]
    return None
