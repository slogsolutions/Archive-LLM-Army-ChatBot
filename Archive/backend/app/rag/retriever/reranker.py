

# IMPROVED VERIOSN

from __future__ import annotations
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.retriever.retriever import SearchResult


def rerank(
    query: str,
    query_embedding: list,
    results: List["SearchResult"],
    intent: str = "mixed",
) -> List["SearchResult"]:
    """
    Intent-aware reranker: boosts results matching query intent.
    
    🔥 NEW: Uses query intent to selectively boost ListItem or Chunk results.
    
    Strategy:
      - For "command" intent: boost ListItem results (structured commands)
      - For "prose" intent: boost Chunk results (prose text)
      - For "list" intent: boost ListItem + sort by rank_in_section
      - For "mixed": just normalize (original behavior)
    
    Args:
        query: original query string
        query_embedding: embedding vector
        results: list of SearchResult objects
        intent: "command" | "prose" | "list" | "mixed"
    
    Returns:
        Reranked results sorted by boosted score.
    
    Examples:
        Query: "find command 5 in File Commands"
        Intent: "command"
        Action: Boost is_list_item=True results by 1.5x
        
        Query: "explain how to use ls"
        Intent: "mixed"
        Action: No boosting, just normalize
    """
    if not results:
        return results

    # ── Step 1: Normalize ES scores to [0, 1] ──────────────────────────────
    scores = [r.score for r in results]
    min_s = min(scores) if scores else 0
    max_s = max(scores) if scores else 0

    if max_s == min_s:
        normalized_scores = [1.0] * len(results)
    else:
        spread = max_s - min_s
        normalized_scores = [(s - min_s) / spread for s in scores]

    # ── Step 2: Apply intent-specific boosting ─────────────────────────────
    boosted_scores = []
    
    for i, r in enumerate(results):
        base_score = normalized_scores[i]
        boost_factor = 1.0
        
        if intent == "command":
            # Boost command results (structured ListItem)
            if r.is_list_item:
                boost_factor = 1.5  # 50% boost for commands
            else:
                boost_factor = 0.8  # Slight penalty for prose in command intent
        
        elif intent == "prose":
            # Boost prose results (Chunk, not ListItem)
            if not r.is_list_item and r.category == "prose":
                boost_factor = 1.5
            else:
                boost_factor = 0.8
        
        elif intent == "list":
            # Boost ListItem results and sort by rank
            if r.is_list_item:
                boost_factor = 1.5
                # Extra boost if rank is low (closer to 1)
                if r.rank_in_section and r.rank_in_section <= 5:
                    boost_factor = 1.8
            else:
                boost_factor = 0.7
        
        # No special boosting for "mixed" intent
        
        boosted_score = base_score * boost_factor
        boosted_scores.append(boosted_score)
        r.score = round(boosted_score, 4)

    # ── Step 3: Sort by boosted score ──────────────────────────────────────
    results.sort(key=lambda r: r.score, reverse=True)
    
    return results


def score_by_relevance(
    query_embedding: list,
    result_embedding: list,
    lexical_score: float = None,
) -> float:
    """
    Alternative: Score by semantic similarity (cosine distance) + lexical score.
    
    Use if you want explicit semantic reranking instead of ES scores.
    Currently, ES hybrid search already combines BM25 + KNN, so this is optional.
    """
    if not query_embedding or not result_embedding:
        return 0.0
    
    # Cosine similarity (assuming embeddings are normalized)
    semantic_score = sum(q * r for q, r in zip(query_embedding, result_embedding))
    
    # Combine with lexical score if provided
    if lexical_score is not None:
        combined = 0.6 * semantic_score + 0.4 * lexical_score
        return round(combined, 4)
    
    return round(semantic_score, 4)


# ============================================================================
# INTENT-AWARE BOOSTING TABLE
# ============================================================================

# Reference: how different result types affect scores based on intent
INTENT_BOOST_TABLE = {
    "command": {
        "is_list_item": True,  # Boost
        "boost_factor": 1.5,
        "description": "Looking for specific commands"
    },
    "prose": {
        "is_list_item": False,  # Boost
        "boost_factor": 1.5,
        "description": "Looking for background/explanation"
    },
    "list": {
        "is_list_item": True,  # Boost
        "boost_factor": 1.5,
        "description": "Looking for all commands in category"
    },
    "mixed": {
        "boost_factor": 1.0,  # No boosting
        "description": "General query, use base scores"
    }
}


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    from app.rag.retriever.retriever import SearchResult
    
    # Mock results
    results = [
        SearchResult(
            doc_id=1,
            content="ls -al command",
            score=0.9,
            page_number=1,
            chunk_index=0,
            heading="File Commands",
            file_name="commands.pdf",
            branch="HQ",
            doc_type="reference",
            year=2026,
            section="File Commands",
            hq_id=1,
            unit_id=1,
            # 🔥 ListItem
            command="ls -al",
            description="Formatted listing with hidden files",
            rank_in_section=2,
            category="file_commands",
            is_list_item=True,
        ),
        SearchResult(
            doc_id=2,
            content="The ls command is used to list files...",
            score=0.85,
            page_number=2,
            chunk_index=1,
            heading="Introduction to File Operations",
            file_name="commands.pdf",
            branch="HQ",
            doc_type="reference",
            year=2026,
            section="File Commands",
            hq_id=1,
            unit_id=1,
            # Prose chunk
            category="prose",
            is_list_item=False,
        ),
    ]
    
    # Test 1: Command intent (should boost ListItem)
    print("Test 1: Command intent")
    reranked = rerank("find command ls", [0.1]*768, results.copy(), intent="command")
    for r in reranked:
        print(f"  Score: {r.score}, Is ListItem: {r.is_list_item}, Command: {r.command}")
    print()
    
    # Test 2: Prose intent (should boost Chunk)
    print("Test 2: Prose intent")
    reranked = rerank("explain ls", [0.1]*768, results.copy(), intent="prose")
    for r in reranked:
        print(f"  Score: {r.score}, Is ListItem: {r.is_list_item}")
    print()