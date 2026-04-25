from __future__ import annotations
"""
Query Rewriting for Army RAG — Stage 2b of the pipeline.

Three techniques, all optional and stackable:

  1. AbbreviationExpander  — "CASEVAC" → "CASEVAC casualty evacuation"
  2. HyDE                  — embed a fake ideal answer instead of the raw query
  3. MultiQuery            — generate N paraphrases, merge retrieved results

In production these run before embedding (Stage 3).  The retriever calls
rewrite_query() which orchestrates whichever techniques are enabled.

Integration point in retriever.py:
  Before:   clean_query = parsed["query"]
  After:    clean_query, hyde_embedding = rewrite_query(parsed["query"], intent)
  Then pass hyde_embedding to hybrid_search() instead of the query embedding.
"""

import re
import requests
import json
from typing import Optional

# ---------------------------------------------------------------------------
# Army-specific abbreviation expansion table
# ---------------------------------------------------------------------------
_ARMY_ABBR: dict[str, str] = {
    # General military
    "co":       "commanding officer CO",
    "oc":       "officer commanding OC",
    "nco":      "non commissioned officer NCO",
    "jco":      "junior commissioned officer JCO",
    "hq":       "headquarters HQ",
    "sos":      "standing operating procedures SOS",
    "sop":      "standard operating procedure SOP",
    "sitrep":   "situation report SITREP",
    "casevac":  "casualty evacuation CASEVAC",
    "medevac":  "medical evacuation MEDEVAC",
    "op":       "operation OP",
    "recce":    "reconnaissance RECCE",
    "fup":      "forming up place FUP",
    "ren":      "rendezvous REN",
    "loc":      "line of communication LOC",
    "lo":       "liaison officer LO",
    "rai":      "rank and insignia RAI",
    "amc":      "army medical corps AMC",
    "asc":      "army service corps ASC",
    "aoc":      "army ordnance corps AOC",
    "emei":     "equipment manufacturers engineering instruction EMEI",
    "mot":      "mechanised organisation transport MOT",

    # Signals
    "rtg":      "radio telephony RTG",
    "comms":    "communications COMMS",
    "freq":     "frequency FREQ",
    "vhf":      "very high frequency VHF",
    "uhf":      "ultra high frequency UHF",
    "net":      "radio net NET",

    # Engineering / IT
    "ls":       "ls list directory files command",
    "pwd":      "pwd print working directory command",
    "mkdir":    "mkdir make directory command",
    "chmod":    "chmod change file permissions command",
    "grep":     "grep search text pattern command",
    "ssh":      "ssh secure shell remote login command",
    "ip":       "ip network interface command",

    # Documents
    "afms":     "army field manual AFMS",
    "iaft":     "indian army field training IAFT",
    "pai":      "part I orders PAI",
    "paii":     "part II orders PAII",
}

# Compile a single regex that matches any abbreviation as a whole word
_ABBR_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _ARMY_ABBR) + r")\b",
    re.IGNORECASE,
)


def expand_abbreviations(query: str) -> str:
    """
    Replace known military abbreviations with expanded forms.

    The expansion appends the full form AFTER the abbreviation so that
    both exact-match (BM25) and semantic (KNN) signals are preserved.

    Example:
        "CASEVAC procedure"  →  "CASEVAC casualty evacuation procedure"
        "ls command"         →  "ls list directory files command command"
    """
    def _replace(m: re.Match) -> str:
        key = m.group(0).lower()
        return _ARMY_ABBR.get(key, m.group(0))

    expanded = _ABBR_PATTERN.sub(_replace, query)

    if expanded != query:
        print(f"[REWRITER] Expanded: {query!r} → {expanded!r}")

    return expanded


# ---------------------------------------------------------------------------
# HyDE — Hypothetical Document Embedding
# ---------------------------------------------------------------------------

_HYDE_SYSTEM = """\
You are an Indian Army document expert.
Generate a SHORT, realistic passage (2-4 sentences) that would appear in an
official army manual and directly answer the question below.
Write ONLY the passage — no preamble, no explanation.
"""


def generate_hyde_passage(query: str, model: str = "llama3:latest") -> Optional[str]:
    """
    Generate a hypothetical document passage for the query using the LLM,
    then return it as a string.  The caller embeds this string instead of
    (or in addition to) the raw query for better KNN recall.

    Why this works:
    - Raw query "CASEVAC procedure" is short and sparse → weak KNN signal.
    - A 3-sentence hypothetical passage has much richer vocabulary →
      its embedding lands closer to the real document chunks.

    Returns None if Ollama is unavailable (caller falls back to raw query).
    """
    try:
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _HYDE_SYSTEM},
                    {"role": "user",   "content": f"Question: {query}"},
                ],
                "stream": False,
                "options": {"temperature": 0.4, "num_predict": 200},
            },
            timeout=180,
        )
        resp.raise_for_status()
        passage = resp.json()["message"]["content"].strip()
        print(f"[REWRITER] HyDE passage ({len(passage)} chars): {passage[:80]}…")
        return passage
    except Exception as e:
        print(f"[REWRITER] HyDE failed (falling back to raw query): {e}")
        return None


# ---------------------------------------------------------------------------
# Multi-query generation
# ---------------------------------------------------------------------------

_MULTIQUERY_SYSTEM = """\
You are an Indian Army document search assistant.
Generate exactly 3 alternative phrasings of the question below.
Output ONLY the 3 questions, one per line, no numbering, no explanation.
"""


def generate_query_variants(query: str, model: str = "llama3:latest") -> list[str]:
    """
    Generate 3 paraphrases of the query.

    Used by multi-query retrieval: retrieve for each variant, merge all
    results (deduplicate by doc_id + chunk_index), then rerank the union.

    Returns [original_query] if LLM call fails.
    """
    try:
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _MULTIQUERY_SYSTEM},
                    {"role": "user",   "content": f"Question: {query}"},
                ],
                "stream": False,
                "options": {"temperature": 0.5, "num_predict": 150},
            },
            timeout=180,
        )
        resp.raise_for_status()
        raw = resp.json()["message"]["content"].strip()
        variants = [line.strip() for line in raw.split("\n") if line.strip()][:3]
        print(f"[REWRITER] Multi-query variants: {variants}")
        return variants if variants else [query]
    except Exception as e:
        print(f"[REWRITER] Multi-query failed: {e}")
        return [query]


# ---------------------------------------------------------------------------
# Orchestrator — called from retriever.py
# ---------------------------------------------------------------------------

def rewrite_query(
    query: str,
    intent: str = "mixed",
    use_hyde: bool = True,
    use_expansion: bool = True,
    model: str = "llama3:latest",
) -> tuple[str, Optional[str]]:
    """
    Stage 2b: Rewrite the query before embedding.

    Returns
    -------
    (search_query, hyde_passage)

    search_query  : Expanded query string for BM25 text search
    hyde_passage  : Hypothetical passage for KNN embedding (or None → use search_query)

    The caller (retriever.py) should:
      - Embed hyde_passage if not None, else embed search_query
      - Use search_query for the BM25 text match field

    Intent-based behaviour:
    - "command" intent → skip HyDE (exact match is better here)
    - "prose"   intent → HyDE gives the biggest boost
    - "list"    intent → expansion only (lists need exact terms)
    - "mixed"   intent → expansion + HyDE
    """
    search_query = query

    # Step 1: Abbreviation expansion (always safe, fast, no LLM needed)
    if use_expansion:
        search_query = expand_abbreviations(search_query)

    # Step 2: HyDE — skip for command/list intent (exact match wins there)
    hyde_passage: Optional[str] = None
    if use_hyde and intent in ("prose", "mixed"):
        hyde_passage = generate_hyde_passage(query, model=model)

    return search_query, hyde_passage