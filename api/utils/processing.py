"""
Document processing utilities for technical documentation.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Set
from langchain_text_splitters import RecursiveCharacterTextSplitter
from collections import defaultdict

from .extraction import extract_technical_terms

__all__ = [
    "process_markdown_text",
    "create_markdown_chunker",
    "detect_content_types",
    "extract_page_number",
    "normalize_metadata_for_vectorstore",
    "normalize_pdf_id",
    "normalize_research_metadata"
]

logger = logging.getLogger(__name__)


def normalize_pdf_id(pdf_id) -> str:
    """Ensure PDF ID is always a string."""
    if pdf_id is None:
        return ""
    return str(pdf_id)


def normalize_research_metadata(metadata_dict: dict) -> dict:
    """
    Normalize research metadata to ensure consistent structure.
    This handles various formats of metadata that might exist in the system.

    Args:
        metadata_dict: Raw metadata dictionary

    Returns:
        Normalized metadata dictionary with consistent research mode structure
    """
    if not metadata_dict:
        return {}

    normalized = metadata_dict.copy()

    # Handle case where research_mode might be a boolean instead of dict
    if "research_mode" in normalized and not isinstance(normalized["research_mode"], dict):
        is_active = bool(normalized["research_mode"])
        normalized["research_mode"] = {
            "active": is_active,
            "pdf_ids": []
        }

    # Handle case where research_mode is missing but active_pdf_ids exists
    if "research_mode" not in normalized and "active_pdf_ids" in normalized:
        pdf_ids = normalized["active_pdf_ids"]
        normalized["research_mode"] = {
            "active": len(pdf_ids) > 1,
            "pdf_ids": pdf_ids
        }

    # Ensure research_mode dict has proper structure if it exists
    if "research_mode" in normalized and isinstance(normalized["research_mode"], dict):
        research_mode = normalized["research_mode"]

        # Ensure active field exists
        if "active" not in research_mode:
            # Try to determine from pdf_ids
            pdf_ids = research_mode.get("pdf_ids", [])
            research_mode["active"] = len(pdf_ids) > 1

        # Ensure pdf_ids exists
        if "pdf_ids" not in research_mode:
            # Try to get from active_pdf_ids
            if "active_pdf_ids" in normalized:
                research_mode["pdf_ids"] = normalized["active_pdf_ids"]
            else:
                research_mode["pdf_ids"] = []

        # Ensure document_names exists
        if "document_names" not in research_mode:
            research_mode["document_names"] = {}

    return normalized


def process_markdown_text(
    text: str,
    chunk_size: int = 400,
    chunk_overlap: int = 50
) -> List[Dict[str, Any]]:
    """
    Process markdown text into chunks with hierarchical awareness.

    Args:
        text: The markdown text to process
        chunk_size: Target size for each chunk
        chunk_overlap: Number of characters to overlap between chunks

    Returns:
        List of chunks with metadata
    """
    # Create markdown-aware text splitter
    splitter = create_markdown_chunker(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        strip_whitespace=True
    )

    # Split text into chunks
    chunks = splitter.split_text(text)

    # Process chunks with metadata
    processed_chunks = []
    section_stack = []  # Track current section hierarchy

    for i, chunk_text in enumerate(chunks):
        # Extract section headers
        header_match = re.search(r'^(#{1,6})\s+(.+)$', chunk_text, re.MULTILINE)
        if header_match:
            level = len(header_match.group(1))
            header_text = header_match.group(2).strip()

            # Update section stack based on header level
            while section_stack and len(section_stack) >= level:
                section_stack.pop()
            section_stack.append(header_text)

        # Extract technical terms
        technical_terms = extract_technical_terms(chunk_text)

        # Detect content types
        content_types = detect_content_types(chunk_text)

        # Create chunk metadata
        metadata = {
            "chunk_index": i,
            "section_headers": list(section_stack),
            "technical_terms": technical_terms,
            "content_types": content_types,
            "page_number": extract_page_number(chunk_text),
            "has_code": "code" in content_types,
            "has_table": "table" in content_types,
            "has_image": "image" in content_types,
            "hierarchy_level": len(section_stack)
        }

        # Create processed chunk
        processed_chunks.append({
            "content": chunk_text,
            "metadata": metadata
        })

    return processed_chunks


def create_markdown_chunker(
    chunk_size: int = 400,
    chunk_overlap: int = 50,
    strip_whitespace: bool = True
) -> RecursiveCharacterTextSplitter:
    """
    Create an enhanced markdown-aware text splitter optimized for technical documentation.

    Args:
        chunk_size: Target size for each chunk (in characters)
        chunk_overlap: Number of characters to overlap between chunks
        strip_whitespace: Whether to strip whitespace from the start/end of chunks

    Returns:
        RecursiveCharacterTextSplitter configured for Markdown
    """
    # Define enhanced markdown separators in order of priority
    # Optimized for technical documentation structure
    markdown_separators = [
        # Headers (preserves document structure)
        "\n# ",     # H1
        "\n## ",    # H2
        "\n### ",   # H3
        "\n#### ",  # H4
        "\n##### ", # H5

        # Code blocks (keep intact)
        "\n```\n",
        "\n```",

        # Tables (keep intact)
        "\n|",

        # Paragraph breaks (natural breaking points)
        "\n\n",

        # List items (respect list structure)
        "\n- ",
        "\n* ",
        "\n+ ",
        "\n1. ",
        "\n2. ",

        # Horizontal rules (natural section dividers)
        "\n---\n",
        "\n___\n",

        # Sentence breaks (lower priority)
        ". ",
        "! ",
        "? ",

        # Last resort (word breaks)
        " ",
        ""
    ]

    # Create the recursive text splitter with enhanced separators
    return RecursiveCharacterTextSplitter(
        separators=markdown_separators,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        keep_separator=True,
        strip_whitespace=strip_whitespace
    )


def detect_content_types(text: str) -> List[str]:
    """
    Detect content types present in text with enhanced recognition patterns.
    Optimized for technical documentation including Niagara framework elements.

    Args:
        text: Text to analyze

    Returns:
        List of detected content types
    """
    content_types = ["text"]  # Text is always present

    # Check for images (Markdown image syntax)
    if re.search(r'!\[.*?\]\(.*?\)', text):
        content_types.append("image")

    # Check for tables (Markdown table syntax)
    if re.search(r'\|.*\|[\s]*\n\|[\s]*[-:]+[-|\s:]*\|', text, re.MULTILINE):
        content_types.append("table")

    # Check for code blocks
    if re.search(r'```\w*\n[\s\S]*?```', text) or re.search(r'`[^`]+`', text):
        content_types.append("code")

    # Check for mathematical equations
    if re.search(r'\$\$[\s\S]*?\$\$', text) or re.search(r'\$[^\$]+\$', text):
        content_types.append("equation")

    # Check for diagrams (mermaid, etc.)
    if "```mermaid" in text or "```plantuml" in text:
        content_types.append("diagram")

    # Niagara-specific content types
    if re.search(r'(SeriesTransform|TimeShift|Trend\s+Chart|Historian|History\s+Config)', text, re.IGNORECASE):
        content_types.append("trend_data")

    if re.search(r'(Wire\s+Sheet|Logic\s+Diagram|Function\s+Block|BajaScript)', text, re.IGNORECASE):
        content_types.append("programming")

    if re.search(r'(Hierarchy|Nav\s+Tree|Station|JACE)', text, re.IGNORECASE):
        content_types.append("building_automation")

    return content_types


def extract_page_number(text: str) -> Optional[int]:
    """
    Extract page number from text with enhanced pattern matching.

    Args:
        text: Text to extract page number from

    Returns:
        Page number if found, otherwise None
    """
    # Enhanced patterns for page number detection
    patterns = [
        r"(?:Page|PAGE)[\s]*(\d+)",
        r"(?:Pg\.|pg\.)[\s]*(\d+)",
        r"-\s*(\d+)\s*-",  # Center page numbers like "- 42 -"
        r"\[Page\s*(\d+)\]", # [Page 42] format
        r"\(Page\s*(\d+)\)", # (Page 42) format
        r"(?:Page|PAGE)[\s]*(\d+)[\s]*(?:of|OF)[\s]*\d+",  # "Page X of Y" format
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue

    return None


def normalize_metadata_for_vectorstore(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize metadata to be compatible with vector store requirements.
    Centralizes metadata normalization in one place.

    Args:
        metadata: Original metadata dictionary

    Returns:
        Normalized metadata dictionary compatible with vector stores
    """
    if not metadata:
        return {}

    normalized = {}

    for key, value in metadata.items():
        # Skip null values and empty collections
        if value is None or (hasattr(value, '__len__') and len(value) == 0):
            continue

        # Handle arrays/lists
        if isinstance(value, (list, tuple, set)):
            # Convert to list if it's not already
            value_list = list(value)

            # Empty list case
            if not value_list:
                continue

            # If list has a single numeric value, extract it
            if len(value_list) == 1 and isinstance(value_list[0], (int, float)):
                normalized[key] = float(value_list[0])
            # For list of numbers, convert to strings
            elif all(isinstance(item, (int, float)) for item in value_list):
                normalized[key] = [str(item) for item in value_list]
            # For list of strings, keep as is
            elif all(isinstance(item, str) for item in value_list):
                # Ensure strings aren't too long for vector store
                normalized[key] = [str(item)[:500] for item in value_list]
            # For mixed or other lists, convert to strings
            else:
                try:
                    normalized[key] = [str(item)[:500] for item in value_list]
                except:
                    # Skip if conversion fails
                    continue

        # Handle primitive types (directly supported)
        elif isinstance(value, (str, int, float, bool)):
            # Truncate long strings
            if isinstance(value, str) and len(value) > 500:
                normalized[key] = value[:500]
            else:
                normalized[key] = value

        # Dictionary case - convert to string representation
        elif isinstance(value, dict):
            try:
                # Convert dict to a string but limit length
                dict_str = str(value)
                normalized[key] = dict_str[:500] if len(dict_str) > 500 else dict_str
            except:
                continue

        # All other types - convert to string
        else:
            try:
                normalized[key] = str(value)[:500]
            except:
                continue

    return normalized
