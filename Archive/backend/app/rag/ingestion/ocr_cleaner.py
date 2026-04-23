from __future__ import annotations
import re


def clean_ocr_text(text: str) -> str:
    """
    Production-grade OCR text cleaning.
    Fixes artifacts while preserving structure.
    
    BEFORE:
      "1 ls Directory listing
       2 ls al Formatted..."
    
    AFTER:
      "1. ls Directory listing
       2. ls -al Formatted..."
    """
    if not text:
        return ""

    # Step 1: Remove control characters (keep newlines)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Step 2: Fix broken hyphens
    # "secu-\nrity" → "security"
    text = re.sub(r"-\n(\w)", r"\1", text)

    # Step 3: Fix missing hyphens in commands
    # "ls al" → "ls -al", "ls lt" → "ls -lt"
    text = re.sub(r"\bls\s+(al|lt|a|l)\b", lambda m: f"ls -{m.group(1)}", text)

    # Step 4: Normalize spacing
    text = re.sub(r"[ \t]+", " ", text)

    # Step 5: Collapse excessive newlines (keep paragraph breaks)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Step 6: Strip whitespace from lines
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()


def recover_list_structure(text: str) -> str:
    """
    Recover numbered lists when OCR strips the dots.
    
    Detects: "1 command_text description"
    Outputs: "1. command_text description"
    
    BEFORE (OCR output):
      "1 ls Directory listing
       2 ls -al Formatted listing
       3 ls -lt Sorting listing"
    
    AFTER (recovered):
      "1. ls Directory listing
       2. ls -al Formatted listing
       3. ls -lt Sorting listing"
    
    Returns original text if no list structure detected.
    """
    if not text.strip():
        return text

    lines = text.split("\n")
    recovered_lines = []
    list_detected = False
    
    for line in lines:
        stripped = line.strip()
        
        # Match: starts with digit(s), space, non-digit
        # Examples: "1 ls", "2 ls -al", "10 command"
        match = re.match(r"^(\d+)\s+([a-z\-\.\$#][^\n]*)$", stripped, re.IGNORECASE)
        
        if match:
            rank = match.group(1)
            rest = match.group(2).strip()
            
            # Check if this looks like a command (short first token)
            first_token = rest.split()[0] if rest.split() else ""
            if len(first_token) < 30:  # Commands are usually short
                list_detected = True
                recovered_lines.append(f"{rank}. {rest}")
            else:
                recovered_lines.append(stripped)
        else:
            recovered_lines.append(stripped)
    
    if not list_detected:
        return text  # Return original if no list detected
    
    return "\n".join(recovered_lines)


def detect_list_sections(text: str) -> list[tuple[int, int, str]]:
    """
    Detect numbered list sections in text.
    
    Returns:
        List of (start_line, end_line, section_heading) tuples
    
    Example:
        text = '''
        File Commands
        1. ls Directory listing
        2. ls -al Formatted...
        
        Process Management
        1. ps Display processes
        2. kill Kill process
        '''
        
        result: [
            (1, 2, "File Commands"),
            (4, 5, "Process Management")
        ]
    """
    lines = text.split("\n")
    sections = []
    current_section = ""
    section_start = None
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Detect section heading (all caps or title case, no content after)
        is_heading = (
            stripped and 
            len(stripped) < 100 and
            (stripped.isupper() or (stripped.istitle() and not stripped.endswith(".")))
        )
        
        # Detect list item: "1. item" or "1 item"
        is_list_item = re.match(r"^\d+[\.\s]\s*\w", stripped)
        
        if is_heading:
            # Save previous section if exists
            if section_start is not None:
                sections.append((section_start, i - 1, current_section))
            current_section = stripped
            section_start = None
        elif is_list_item and section_start is None:
            section_start = i
        elif is_list_item:
            # Continue in current section
            pass
        elif section_start is not None and stripped:
            # Non-list item in the middle → end section
            sections.append((section_start, i - 1, current_section))
            section_start = None
    
    # Finalize last section
    if section_start is not None:
        sections.append((section_start, len(lines) - 1, current_section))
    
    return sections


def apply_ocr_pipeline(text: str) -> str:
    """
    Full OCR cleanup pipeline (recommended).
    
    Steps:
    1. Clean artifacts (hyphenation, spacing, etc.)
    2. Recover list structure (add missing dots/numbers)
    3. Return cleaned, structured text
    
    Use this in worker.py:
        ocr_text = run_ocr_on_pdf(local_path)
        ocr_text = apply_ocr_pipeline(ocr_text)  # ← Insert here
        doc.ocr_text = ocr_text
    """
    text = clean_ocr_text(text)
    text = recover_list_structure(text)
    return text


# ============================================================================
# VALIDATION & METRICS
# ============================================================================

def estimate_ocr_quality(text: str) -> dict:
    """
    Estimate OCR quality by looking for common issues.
    
    Returns dict with:
        - has_list_structure: bool (detected numbered lists?)
        - artifact_count: int (estimated OCR errors)
        - quality_score: float (0.0-1.0)
        - issues: list[str] (warnings)
    
    Example:
        quality = estimate_ocr_quality(ocr_text)
        if quality["quality_score"] < 0.6:
            print(f"⚠️  Low OCR quality: {quality['issues']}")
    """
    issues = []
    artifacts = 0
    
    # Check for missing dots after numbers
    missing_dots = len(re.findall(r"^\d+\s+[a-z]", text, re.MULTILINE))
    if missing_dots > 3:
        issues.append(f"Missing dots after numbers ({missing_dots} cases)")
        artifacts += missing_dots
    
    # Check for hyphenation artifacts
    hyphens = len(re.findall(r"-\n\w", text))
    if hyphens > 2:
        issues.append(f"Broken hyphenation ({hyphens} cases)")
        artifacts += hyphens
    
    # Check for spacing issues
    double_spaces = len(re.findall(r"  +", text))
    if double_spaces > 10:
        issues.append(f"Excessive spacing ({double_spaces} cases)")
    
    # Check for list structure
    has_lists = bool(re.search(r"^\d+[\.\s]\s+\w", text, re.MULTILINE))
    
    # Calculate quality score (0-1)
    # Penalize for each artifact, bonus for list structure
    quality_score = 1.0
    quality_score -= min(artifacts * 0.05, 0.3)  # Max -30%
    if has_lists:
        quality_score += 0.1  # Bonus if structure detected
    quality_score = max(0.0, min(1.0, quality_score))
    
    return {
        "has_list_structure": has_lists,
        "artifact_count": artifacts,
        "quality_score": round(quality_score, 2),
        "issues": issues,
    }


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    # Test 1: Clean OCR artifacts
    test1 = """
    1 ls Directory listing
    2 ls al Formatted listing
    3 ls lt Sorting
    """
    print("TEST 1: Recover list structure")
    print("BEFORE:", repr(test1))
    result1 = recover_list_structure(test1)
    print("AFTER:", repr(result1))
    print()
    
    # Test 2: Full pipeline
    test2 = """
    File Commands
    1 ls Directory listing
    2 ls al Formatted listing with hidden files
    3 ls lt Sorting the formatted listing by time modifi-
    cation
    
    Process management
    1 ps To display the currently working processes
    2 top Display all running process
    """
    print("TEST 2: Full OCR pipeline")
    result2 = apply_ocr_pipeline(test2)
    print("RESULT:")
    print(result2)
    print()
    
    # Test 3: Quality estimation
    quality = estimate_ocr_quality(test2)
    print("TEST 3: Quality estimation")
    print(f"Score: {quality['quality_score']}")
    print(f"Has lists: {quality['has_list_structure']}")
    print(f"Issues: {quality['issues']}")