"""Homophone / mishear-candidate generation.

A small built-in PHONETIC_GROUPS table covering common ASR-confusable English
PM/AI terms; the homophone-detector skill extends this via data/homophones.toml
which is loaded by skills.py at startup.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher


PHONETIC_GROUPS: dict[str, list[str]] = {
    "rag":  ["rag", "lag", "rad", "iad", "rack", "rak", "raq"],
    "dag":  ["dag", "dak", "tag", "dac"],
    "dau":  ["dau", "dow", "tau", "dao", "dal"],
    "mau":  ["mau", "mal", "mao"],
    "roi":  ["roi", "rai", "raw", "r o i"],
    "kpi":  ["kpi", "kbi", "kp"],
    "llm":  ["llm", "lm", "l l m", "elm"],
    "gpt":  ["gpt", "gbt", "gp t", "gpc"],
    "api":  ["api", "abi", "a p i", "apl"],
    "sdk":  ["sdk", "stk", "s d k"],
    "sop":  ["sop", "sap", "s o p"],
    "sql":  ["sql", "s q l", "sequel"],
    "etl":  ["etl", "e t l", "atl"],
    "nlp":  ["nlp", "n l p", "nlb"],
    "ocr":  ["ocr", "o c r", "okr"],
    "okr":  ["okr", "o k r", "ocr"],
    "ctr":  ["ctr", "c t r", "ctl"],
    "arpu": ["arpu", "arbu", "a r p u"],
    "aarrr":["aarrr", "ar", "aaar"],
    "agent":["agent", "asian", "aegent", "aging"],
    "prompt":["prompt", "promp", "promnt", "prom"],
    "fine-tuning": ["fine-tuning", "fine tuning", "finetuning", "find tuning"],
    "hallucination": ["hallucination", "halucination", "幻觉"],
    "embedding": ["embedding", "embeddings", "in bedding", "imbedding"],
    "transformer": ["transformer", "trans former", "transfer"],
    "workflow": ["workflow", "work flow", "worklow"],
    "pipeline": ["pipeline", "pipe line", "pipline"],
}


def merge_groups(extra: dict[str, list[str]]) -> None:
    """Merge skill-provided homophones into the live PHONETIC_GROUPS."""
    for canonical, variants in extra.items():
        if canonical in PHONETIC_GROUPS:
            existing = set(PHONETIC_GROUPS[canonical])
            for v in variants:
                if v not in existing:
                    PHONETIC_GROUPS[canonical].append(v)
        else:
            PHONETIC_GROUPS[canonical] = list(variants)


def find_mishear_candidates(query: str) -> list[str]:
    """Suggest alternative spellings of a query using PHONETIC_GROUPS."""
    q_lower = query.lower()
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]*", q_lower)
    canonical_set = set(PHONETIC_GROUPS.keys())
    candidates: list[str] = []
    for word in words:
        if word in canonical_set:
            continue
        for canonical, variants in PHONETIC_GROUPS.items():
            if word in variants:
                candidates.append(q_lower.replace(word, canonical, 1))
            elif 2 <= len(word) <= 8:
                for v in variants:
                    if v == word:
                        continue
                    if SequenceMatcher(None, word, v).ratio() >= 0.6:
                        candidates.append(q_lower.replace(word, canonical, 1))
                        break
    return list(dict.fromkeys(candidates))[:5]
