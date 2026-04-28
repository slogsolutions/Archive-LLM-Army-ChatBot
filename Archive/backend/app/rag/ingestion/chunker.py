from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.ingestion.parser import ParsedPage


# ---------------------------------------------------------------------------
# REGEX — compiled once
# ---------------------------------------------------------------------------

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
# Allow zero or more spaces after dot — handles "6.Mesh Topology" (no space)
LIST_SPLIT  = re.compile(r"\n?(\d+)[\.\)]\s*")


# ---------------------------------------------------------------------------
# DATA CLASSES
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    """A prose text chunk produced by the sliding-window chunker."""
    text: str
    page_number: int
    chunk_index: int
    total_chunks: int = 0
    heading: str = ""
    char_offset: int = 0


@dataclass
class ListItem:
    """
    A single entry from a numbered list (e.g. a CLI command).

    Exposes `.text` as an alias for `.full_text` so that callers
    (pipeline.py, indexer.py) can treat Chunk and ListItem uniformly
    without isinstance checks everywhere.
    """
    rank: int                   # Position in section: 1, 2, 3 …
    command: str                # First token(s): "ls -al"
    description: str            # Rest of the line / following lines
    section: str = ""           # Parent section heading
    category: str = ""          # Auto-detected: "file_commands", "network" …
    full_text: str = ""         # Combined string used for embedding
    page_number: int = 0        # ← same field name as Chunk (pipeline compat)
    chunk_index: int = 0        # ← same field name as Chunk
    total_chunks: int = 1       # ← same field name as Chunk
    heading: str = ""           # ← same field name as Chunk
    char_offset: int = 0        # ← same field name as Chunk

    def __post_init__(self):
        if not self.full_text:
            self.full_text = f"{self.command} {self.description}".strip()

    # ------------------------------------------------------------------
    # Uniform attribute: both Chunk and ListItem expose `.text`
    # ------------------------------------------------------------------
    @property
    def text(self) -> str:
        """Alias for full_text — lets pipeline.py use c.text on both types."""
        return self.full_text

    @text.setter
    def text(self, value: str):
        self.full_text = value


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> List[str]:
    parts = _SENT_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]


def _extract_list_items(text: str, section: str = "") -> List[ListItem]:
    """
    Parse a paragraph that looks like a numbered list and return ListItem
    objects with rank preserved.

    Input
    -----
    1. ls               Directory listing
    2. ls -al           Formatted listing with hidden files
    3. ls -lt           Sort by modification time

    Output
    ------
    [
      ListItem(rank=1, command="ls",    description="Directory listing"),
      ListItem(rank=2, command="ls -al",description="Formatted listing…"),
      …
    ]

    Returns [] if the text does not look like a numbered list.
    """
    if not re.search(r"^\d+[\.\)]\s*\S", text, re.MULTILINE):
        return []

    items: List[ListItem] = []
    parts = LIST_SPLIT.split(text)

    # parts layout: ['', '1', 'ls Directory…', '', '2', 'ls -al …', …]
    i = 1
    while i < len(parts) - 1:
        try:
            rank    = int(parts[i])
            content = parts[i + 1].strip()

            if not content:
                i += 2
                continue

            lines   = content.split("\n")
            command = lines[0].strip()
            description = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

            if not description:
                # CLI-style: "ls -al  Formatted listing" — split on 2+ spaces
                if re.search(r"\s{2,}", command):
                    col_parts = re.split(r"\s{2,}", command, maxsplit=1)
                    command = col_parts[0].strip()
                    description = col_parts[1].strip() if len(col_parts) > 1 else ""
                elif len(command.split()) > 4:
                    # Topic-style: "Mesh Topology Each host has its connections..."
                    # Use first 2-3 words as the topic title, rest as description.
                    words = command.split()
                    # Find a natural break: look for the first word after position 2
                    # that starts a new concept (capital letter after lowercase run)
                    split_at = 3  # default: first 3 words
                    for idx in range(2, min(5, len(words))):
                        if words[idx][0].isupper() and words[idx - 1][-1].islower():
                            split_at = idx
                            break
                    command = " ".join(words[:split_at])
                    description = " ".join(words[split_at:])

            items.append(ListItem(
                rank=rank,
                command=command,
                description=description,
                section=section,
                category=_categorize(command),
                heading=section,           # mirrors Chunk.heading
            ))
        except (ValueError, IndexError):
            pass

        i += 2

    return items


def _categorize(cmd: str) -> str:
    """Heuristic category from command token."""
    c = cmd.lower()
    if any(x in c for x in ["ls", "cd", "pwd", "mkdir", "cat", "cp", "mv", "rm", "touch"]):
        return "file_commands"
    if any(x in c for x in ["ps", "kill", "top", "bg", "fg"]):
        return "process_management"
    if any(x in c for x in ["grep", "find", "locate", "pgrep"]):
        return "searching"
    if any(x in c for x in ["chmod", "chown"]):
        return "permissions"
    if any(x in c for x in ["ping", "wget", "dig", "whois", "curl", "ssh", "netstat", "ifconfig", "ip"]):
        return "network"
    if any(x in c for x in ["tar", "gzip", "zip", "unzip", "bzip2"]):
        return "compression"
    if any(x in c for x in ["ctrl", "exit", "alias", "history"]):
        return "shortcuts"
    if any(x in c for x in ["apt", "yum", "dnf", "pip", "npm"]):
        return "package_management"
    # Army-specific
    if any(x in c for x in ["deploy", "mission", "patrol", "sitrep", "casevac"]):
        return "army_operations"
    return "system_info"


def _is_heading(line: str) -> bool:
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


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def chunk_document(
    pages: List["ParsedPage"],
    chunk_size: int = 350,
    overlap: int = 80,
) -> List[Union[Chunk, ListItem]]:
    """
    Convert parsed pages into a flat list of Chunk | ListItem objects.

    Strategy
    --------
    - Numbered-list paragraphs  → ListItem objects (structure preserved as-is)
    - Prose paragraphs          → sentences fed into sliding-window chunker

    Both types expose `.text`, `.page_number`, `.chunk_index`, `.total_chunks`,
    `.heading`, and `.char_offset` so pipeline.py can iterate them uniformly.

    Returns
    -------
    List[Union[Chunk, ListItem]]
    """
    results:   List[Union[Chunk, ListItem]] = []
    sent_meta: List[tuple[str, int, str]]   = []   # (sentence, page_no, section)

    current_section = ""

    # -----------------------------------------------------------------------
    # PASS 1 — classify each paragraph as list or prose
    # -----------------------------------------------------------------------
    for page in pages:
        text = page.text
        if not text.strip():
            continue

        if page.heading:
            current_section = page.heading

        paragraphs = re.split(r"\n{2,}", text)

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            first_line = para.split("\n")[0].strip()
            if _is_heading(first_line):
                current_section = first_line

            # --- Try list extraction first ---------------------------------
            list_items = _extract_list_items(para, section=current_section)

            if list_items:
                for item in list_items:
                    item.section  = current_section
                    item.heading  = current_section
                    item.page_number = page.page_number
                    results.append(item)
            else:
                # --- Prose: collect sentences for sliding window -----------
                for block in re.split(r"\n{2,}", para):
                    sentences = _split_sentences(block) or [block]
                    for s in sentences:
                        if s.strip():
                            sent_meta.append((s.strip(), page.page_number, current_section))

    # -----------------------------------------------------------------------
    # PASS 2 — section-boundary chunking
    #
    # Group collected sentences by section BEFORE running the sliding window.
    # This prevents cross-section contamination (e.g. a chunk that mixes
    # "General" content with "Allotment of Money" content).
    #
    # Each section's sentences are chunked independently.  The section
    # heading is then PREPENDED to every chunk's text so the embedding
    # model captures "what section this is from" — critical for retrieval.
    #
    # Example output text for a chunk:
    #   "Allotment of Money: The DCOAS will make allotments from this sum
    #    to Commands and Commandants of schools..."
    # -----------------------------------------------------------------------
    if sent_meta:
        # Group sentences by section while preserving order
        section_groups: list[tuple[str, list[tuple[str, int, str]]]] = []
        for entry in sent_meta:
            section = entry[2] or ""
            if section_groups and section_groups[-1][0] == section:
                section_groups[-1][1].append(entry)
            else:
                section_groups.append((section, [entry]))

        for section_name, section_sents in section_groups:
            sec_chunks = _chunk_sentences(
                section_sents, chunk_size=chunk_size, overlap=overlap
            )
            # Prepend the section heading so the embedding captures context
            for c in sec_chunks:
                if section_name and section_name.lower() not in c.text[:80].lower():
                    c.text = f"{section_name}: {c.text}"
                    c.heading = section_name
            results.extend(sec_chunks)

    return results


# ---------------------------------------------------------------------------
# SLIDING-WINDOW CHUNKER (prose only)
# ---------------------------------------------------------------------------

def _chunk_sentences(
    sent_meta: List[tuple[str, int, str]],
    chunk_size: int = 350,
    overlap: int = 80,
) -> List[Chunk]:
    chunks: List[Chunk] = []
    n = len(sent_meta)
    i = 0
    skip_words = max(chunk_size - overlap, 1)

    while i < n:
        word_count = 0
        j = i

        while j < n and word_count < chunk_size:
            word_count += len(sent_meta[j][0].split())
            j += 1

        window     = sent_meta[i:j]
        chunk_text = " ".join(s[0] for s in window)
        page_num   = window[0][1]
        heading    = window[0][2]
        char_off   = sum(len(s[0]) + 1 for s in sent_meta[:i])

        chunks.append(Chunk(
            text=chunk_text,
            page_number=page_num,
            chunk_index=len(chunks),
            heading=heading,
            char_offset=char_off,
        ))

        # Advance by skip_words, but always move at least one sentence forward
        skipped  = 0
        skip_i   = i
        while skip_i < j and skipped < skip_words:
            skipped += len(sent_meta[skip_i][0].split())
            skip_i  += 1
        i = max(skip_i, i + 1)

    total = len(chunks)
    for c in chunks:
        c.total_chunks = total

    return chunks