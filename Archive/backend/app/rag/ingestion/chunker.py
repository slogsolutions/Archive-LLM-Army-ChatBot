# from __future__ import annotations
# import re
# from dataclasses import dataclass
# from typing import List, TYPE_CHECKING

# if TYPE_CHECKING:
#     from app.rag.ingestion.parser import ParsedPage


# # =========================
# # REGEX
# # =========================

# _SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
# LIST_SPLIT = re.compile(r"\n?\d+[\.\)]\s+")


# # =========================
# # DATA CLASS
# # =========================

# @dataclass
# class Chunk:
#     text: str
#     page_number: int
#     chunk_index: int
#     total_chunks: int = 0
#     heading: str = ""
#     char_offset: int = 0


# # =========================
# # HELPERS
# # =========================

# def _split_sentences(text: str) -> List[str]:
#     parts = _SENT_SPLIT.split(text)
#     return [p.strip() for p in parts if p.strip()]


# def _split_structured(text: str) -> List[str]:
#     """
#     Handle numbered lists like:
#     1. ...
#     2. ...
#     """
#     parts = LIST_SPLIT.split(text)

#     return [p.strip() for p in parts if p.strip()]


# def _is_heading(line: str) -> bool:
#     line = line.strip()

#     if not line or len(line) > 120:
#         return False

#     words = line.split()

#     if len(words) > 12:
#         return False

#     return (
#         line.isupper()
#         or (line.istitle() and not line.endswith("."))
#         or (re.match(r"^\d+[\.\)]\s+\w", line) and len(words) <= 8)
#     )


# # =========================
# # MAIN FUNCTION
# # =========================

# def chunk_document(
#     pages: List["ParsedPage"],
#     chunk_size: int = 350,
#     overlap: int = 80,
# ) -> List[Chunk]:

#     sent_meta: List[tuple[str, int, str]] = []
#     current_heading = ""

#     # =========================
#     # STEP 1: STRUCTURE AWARE FLATTEN
#     # =========================
#     for page in pages:
#         text = page.text

#         if not text.strip():
#             continue

#         if page.heading:
#             current_heading = page.heading

#         paragraphs = re.split(r"\n{2,}", text)

#         for para in paragraphs:
#             para = para.strip()
#             if not para:
#                 continue

#             # Detect heading
#             first_line = para.split("\n")[0].strip()
#             if _is_heading(first_line):
#                 current_heading = first_line

#             # 🔥 FIRST split structured lists
#             blocks = _split_structured(para)

#             for block in blocks:

#                 # THEN split sentences
#                 sentences = _split_sentences(block)

#                 if not sentences:
#                     sentences = [block]

#                 for s in sentences:
#                     if s.strip():
#                         sent_meta.append((s.strip(), page.page_number, current_heading))

#     if not sent_meta:
#         return []

#     # =========================
#     # STEP 2: SLIDING WINDOW
#     # =========================
#     chunks: List[Chunk] = []
#     n = len(sent_meta)
#     i = 0

#     while i < n:

#         word_count = 0
#         j = i

#         while j < n and word_count < chunk_size:
#             word_count += len(sent_meta[j][0].split())
#             j += 1

#         chunk_sents = sent_meta[i:j]

#         chunk_text = " ".join(s[0] for s in chunk_sents)
#         page_num = chunk_sents[0][1]
#         heading = chunk_sents[0][2]

#         char_offset = sum(len(s[0]) + 1 for s in sent_meta[:i])

#         chunks.append(Chunk(
#             text=chunk_text,
#             page_number=page_num,
#             chunk_index=len(chunks),
#             heading=heading,
#             char_offset=char_offset,
#         ))

#         # =========================
#         # OVERLAP LOGIC
#         # =========================
#         skip_words = max(chunk_size - overlap, 1)
#         skipped = 0
#         skip_i = i

#         while skip_i < j and skipped < skip_words:
#             skipped += len(sent_meta[skip_i][0].split())
#             skip_i += 1

#         i = max(skip_i, i + 1)

#     # =========================
#     # STEP 3: FINALIZE
#     # =========================
#     total = len(chunks)
#     for c in chunks:
#         c.total_chunks = total

#     return chunks



# IMPROVED VERSION 

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List, Union, TYPE_CHECKING
 
if TYPE_CHECKING:
    from app.rag.ingestion.parser import ParsedPage
 
 
# =========================
# REGEX
# =========================
 
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
LIST_SPLIT = re.compile(r"\n?(\d+)[\.\)]\s+")  # 🔥 CAPTURE the number
 
 
# =========================
# DATA CLASSES
# =========================
 
@dataclass
class Chunk:
    text: str
    page_number: int
    chunk_index: int
    total_chunks: int = 0
    heading: str = ""
    char_offset: int = 0
 
 
@dataclass
class ListItem:
    """Structured representation of a list entry (e.g., numbered command)."""
    rank: int                    # Position in section (1, 2, 3...)
    command: str                 # First line: "ls -al"
    description: str             # Description text
    section: str = ""            # Parent section: "File Commands"
    category: str = ""           # Type: "file_cmd", "process_mgmt", "network"
    full_text: str = ""          # Combined for embedding: "ls -al Formatted listing..."
    
    def __post_init__(self):
        if not self.full_text:
            self.full_text = f"{self.command} {self.description}"
 
 
# =========================
# HELPERS
# =========================
 
def _split_sentences(text: str) -> List[str]:
    """Split by sentence boundaries (periods, !, ?)."""
    parts = _SENT_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]
 
 
def _extract_list_items(text: str, section: str = "") -> List[ListItem]:
    """
    Extract numbered list items with rank preserved.
    
    Input:
        1. ls                Directory listing
        2. ls -al            Formatted listing with hidden files
        3. ls -lt            Sorting...
    
    Output:
        [ListItem(rank=1, command="ls", description="Directory listing"),
         ListItem(rank=2, command="ls -al", description="Formatted listing..."),
         ...]
    
    Returns empty list if text doesn't look like a numbered list.
    """
    # Check if text contains list numbers
    if not re.search(r"^\d+[\.\)]\s+", text, re.MULTILINE):
        return []
    
    items = []
    # Split on numbered prefixes, keeping the number
    parts = LIST_SPLIT.split(text)
    
    # parts = ['', '1', 'ls Directory listing', '', '2', 'ls -al Formatted...', ...]
    # Process pairs: (rank, content)
    i = 1  # Skip empty first element
    while i < len(parts) - 1:
        try:
            rank = int(parts[i])
            content = parts[i + 1].strip()
            
            if not content:
                i += 2
                continue
            
            # Split content into command (first line) and description (rest)
            lines = content.split('\n')
            command = lines[0].strip()
            description = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ""
            
            # If no explicit description, use the same line
            # (for cases like "ls -al  Formatted listing with hidden files")
            if not description and '  ' in command:
                parts_split = command.split(None, 1)
                if len(parts_split) == 2:
                    command = parts_split[0]
                    description = parts_split[1]
            
            item = ListItem(
                rank=rank,
                command=command,
                description=description,
                section=section,
                category=_categorize_command(command),
            )
            items.append(item)
            i += 2
        except (ValueError, IndexError):
            i += 2
    
    return items
 
 
def _categorize_command(cmd: str) -> str:
    """Auto-categorize command by keyword."""
    cmd_lower = cmd.lower()
    
    if any(x in cmd_lower for x in ['ls', 'cd', 'pwd', 'mkdir', 'cat', 'cp', 'mv', 'rm', 'touch']):
        return "file_commands"
    elif any(x in cmd_lower for x in ['ps', 'kill', 'top', 'bg', 'fg']):
        return "process_management"
    elif any(x in cmd_lower for x in ['grep', 'find', 'locate', 'pgrep']):
        return "searching"
    elif any(x in cmd_lower for x in ['chmod', 'chown']):
        return "permissions"
    elif any(x in cmd_lower for x in ['ping', 'wget', 'dig', 'whois']):
        return "network"
    elif any(x in cmd_lower for x in ['tar', 'gzip', 'zip']):
        return "compression"
    elif any(x in cmd_lower for x in ['ctrl', 'exit']):
        return "shortcuts"
    else:
        return "system_info"
 
 
def _is_heading(line: str) -> bool:
    """Detect if a line is a section heading."""
    line = line.strip()
 
    if not line or len(line) > 120:
        return False
 
    words = line.split()
 
    if len(words) > 12:
        return False
 
    return (
        line.isupper()
        or (line.istitle() and not line.endswith("."))
        or (re.match(r"^\d+[\.\)]\s+\w", line) and len(words) <= 8)
    )
 
 
# =========================
# MAIN FUNCTION
# =========================
 
def chunk_document(
    pages: List["ParsedPage"],
    chunk_size: int = 350,
    overlap: int = 80,
) -> List[Union[Chunk, ListItem]]:
    """
    Chunk document, preserving structure for lists.
    
    Returns:
        List of Chunk or ListItem objects.
        - ListItem for numbered lists (preserved as-is, not chunked)
        - Chunk for prose text (chunked by sliding window)
    """
 
    results: List[Union[Chunk, ListItem]] = []
    sent_meta: List[tuple[str, int, str]] = []
    current_heading = ""
    current_section = ""
 
    # =========================
    # STEP 1: EXTRACT STRUCTURE
    # =========================
    for page in pages:
        text = page.text
 
        if not text.strip():
            continue
 
        if page.heading:
            current_heading = page.heading
            current_section = page.heading
 
        paragraphs = re.split(r"\n{2,}", text)
 
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
 
            # Detect section heading
            first_line = para.split("\n")[0].strip()
            if _is_heading(first_line):
                current_section = first_line
 
            # 🔥 TRY LIST EXTRACTION FIRST
            list_items = _extract_list_items(para, section=current_section)
            
            if list_items:
                # This paragraph is a numbered list → keep structure
                for item in list_items:
                    item.section = current_section
                    results.append(item)
            else:
                # This is prose → chunk normally
                blocks = re.split(r'\n{2,}', para)
                
                for block in blocks:
                    sentences = _split_sentences(block)
                    if not sentences:
                        sentences = [block]
                    
                    for s in sentences:
                        if s.strip():
                            sent_meta.append((s.strip(), page.page_number, current_section))
 
    # =========================
    # STEP 2: CHUNK PROSE (sliding window)
    # =========================
    if sent_meta:
        chunks = _chunk_sentences(sent_meta)
        results.extend(chunks)
 
    return results
 
 
def _chunk_sentences(sent_meta: List[tuple[str, int, str]]) -> List[Chunk]:
    """Apply sliding window to prose sentences."""
    chunks: List[Chunk] = []
    n = len(sent_meta)
    i = 0
 
    while i < n:
        word_count = 0
        j = i
 
        while j < n and word_count < 350:  # chunk_size = 350
            word_count += len(sent_meta[j][0].split())
            j += 1
 
        chunk_sents = sent_meta[i:j]
 
        chunk_text = " ".join(s[0] for s in chunk_sents)
        page_num = chunk_sents[0][1]
        heading = chunk_sents[0][2]
 
        char_offset = sum(len(s[0]) + 1 for s in sent_meta[:i])
 
        chunks.append(Chunk(
            text=chunk_text,
            page_number=page_num,
            chunk_index=len(chunks),
            heading=heading,
            char_offset=char_offset,
        ))
 
        # Sliding window overlap: skip ~270 words, keep 80 overlap
        skip_words = 270  # 350 - 80
        skipped = 0
        skip_i = i
 
        while skip_i < j and skipped < skip_words:
            skipped += len(sent_meta[skip_i][0].split())
            skip_i += 1
 
        i = max(skip_i, i + 1)
 
    total = len(chunks)
    for c in chunks:
        c.total_chunks = total
 
    return chunks