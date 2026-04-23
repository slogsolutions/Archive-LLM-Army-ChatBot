# def format_results(results):

#     output = []

#     for r in results:
#         output.append({
#             "text": r.content,
#             "score": r.score,
#             "doc_id": r.doc_id,
#             "page": r.page_number,
#             "heading": r.heading,
#             "file": r.file_name,
#             "branch": r.branch,
#             "type": r.doc_type,
#         })

#     return output

# IMPROVED VERIONS


from __future__ import annotations
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.retriever.retriever import SearchResult


def format_results(results: List["SearchResult"]) -> List[dict]:
    """
    Format SearchResult objects into API-ready JSON.
    
    🔥 NEW: Includes command metadata for structured results.
    
    Returns:
        List of dicts with full metadata for API consumption.
    
    Example output:
        {
            "text": "ls -al Formatted listing with hidden files",
            "score": 0.95,
            "doc_id": 7,
            "page": 1,
            "heading": "File Commands",
            "file": "Linux_Commands.pdf",
            "branch": "Engineering",
            "type": "Command Reference",
            "section": "File Commands",
            "year": 2026,
            
            # 🔥 NEW: Command metadata
            "command": "ls -al",
            "description": "Formatted listing with hidden files",
            "rank": 2,
            "category": "file_commands",
            "is_command": true,
            
            # Display-friendly
            "title": "ls -al (command #2, file_commands)",
        }
    """
    output = []

    for r in results:
        result_dict = {
            # Core content
            "text": r.content,
            "score": round(r.score, 4),
            "doc_id": r.doc_id,
            
            # Positioning
            "page": r.page_number,
            "chunk": r.chunk_index,
            "heading": r.heading,
            
            # Document metadata
            "file": r.file_name,
            "branch": r.branch,
            "type": r.doc_type,
            "section": r.section,
            "year": r.year,
            "hq_id": r.hq_id,
            "unit_id": r.unit_id,
        }
        
        # 🔥 NEW: Command metadata (only if result is a command)
        if r.is_list_item and r.command:
            result_dict.update({
                "command": r.command,
                "description": r.description or "",
                "rank": r.rank_in_section,
                "category": r.category or "unknown",
                "is_command": True,
                "title": r.get_display_title(),  # "ls -al (command #2, file_commands)"
            })
        else:
            result_dict.update({
                "is_command": False,
                "title": r.get_display_title(),  # Heading or content preview
            })
        
        output.append(result_dict)

    return output


def format_command_results(results: List["SearchResult"]) -> List[dict]:
    """
    Format results optimized for command queries.
    Strips prose/non-command results, formats commands clearly.
    
    Returns only ListItem results with full command details.
    """
    output = []
    
    for r in results:
        if not r.is_list_item or not r.command:
            continue
        
        output.append({
            "command": r.command,
            "description": r.description or "",
            "rank": r.rank_in_section,
            "category": r.category or "",
            "section": r.section,
            "file": r.file_name,
            "score": round(r.score, 4),
            "usage": f"{r.rank_in_section}. {r.command} - {r.description}",
        })
    
    return output


def format_verbose(results: List["SearchResult"], include_full_text: bool = False) -> List[dict]:
    """
    Verbose output with all available metadata.
    
    Useful for debugging or detailed result inspection.
    """
    output = []
    
    for r in results:
        item = {
            # Core
            "doc_id": r.doc_id,
            "score": round(r.score, 4),
            "title": r.get_display_title(),
            
            # Content
            "text": r.content if include_full_text else r.content[:200] + "...",
            "heading": r.heading,
            
            # Position
            "location": {
                "file": r.file_name,
                "page": r.page_number,
                "chunk": r.chunk_index,
                "section": r.section,
            },
            
            # Classification
            "classification": {
                "branch": r.branch,
                "type": r.doc_type,
                "year": r.year,
                "hq_id": r.hq_id,
                "unit_id": r.unit_id,
            },
            
            # Command metadata (if applicable)
            "command_info": {
                "is_command": r.is_list_item,
                "command": r.command,
                "description": r.description,
                "rank_in_section": r.rank_in_section,
                "category": r.category,
            } if r.is_list_item else None,
        }
        
        output.append(item)
    
    return output


def format_minimal(results: List["SearchResult"]) -> List[dict]:
    """
    Minimal output: just essentials.
    """
    return [
        {
            "text": r.content[:100],
            "score": round(r.score, 4),
            "file": r.file_name,
            "command": r.command if r.is_list_item else None,
        }
        for r in results
    ]


# ============================================================================
# JSON SCHEMA (for API documentation)
# ============================================================================

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        # Core content & scoring
        "text": {"type": "string", "description": "Chunk content or command description"},
        "score": {"type": "number", "description": "Relevance score (0-1)"},
        "doc_id": {"type": "integer", "description": "Document ID"},
        
        # Positioning
        "page": {"type": "integer"},
        "chunk": {"type": "integer"},
        "heading": {"type": "string"},
        
        # Document metadata
        "file": {"type": "string"},
        "branch": {"type": "string"},
        "type": {"type": "string"},
        "section": {"type": "string"},
        "year": {"type": "integer"},
        
        # Command metadata (optional)
        "command": {"type": "string", "description": "Command (e.g., 'ls -al')"},
        "description": {"type": "string"},
        "rank": {"type": "integer", "description": "Position in section (1, 2, 3...)"},
        "category": {"type": "string", "description": "Command category"},
        "is_command": {"type": "boolean"},
        
        # Display-friendly
        "title": {"type": "string", "description": "Human-readable title"},
    }
}