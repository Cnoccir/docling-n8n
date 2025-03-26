"""
Utilities for the LangGraph-based PDF RAG system.
"""

# Core utilities for document processing
from .tokenization import (
    get_tokenizer,
    OpenAITokenizerWrapper
)

# Extraction utilities
from .extraction import (
    extract_technical_terms,
    extract_concept_relationships,
    extract_hierarchy_relationships,
    find_best_term_match,
    RelationType
)

# Processing utilities
from .processing import (
    process_markdown_text,
    create_markdown_chunker,
    normalize_metadata_for_vectorstore,
    normalize_pdf_id,
    detect_content_types
)

# Document utilities
from .document import (
    generate_document_summary,
    create_directory_if_not_exists,
    generate_file_hash
)

# LangGraph helpers
from .langgraph_helpers import (
    extract_technical_terms_simple,
    format_conversation_for_llm,
    parse_citations_from_text,
    elements_to_context,
    create_empty_graph_state
)

# PDF status utilities
from .pdf_status import (
    check_pdf_status,
    get_recent_pdfs
)

# Serialization utilities
from .serialization import (
    save_json,
    load_json,
    create_message_from_dict,
    serialize_message
)

# Logging setup
from .logging import (
    setup_logging,
    get_processor_metrics
)

# Async helpers
from .async_helpers import (
    with_timeout,
    run_async,
    to_async,
    to_sync,
    AsyncExecutor,
    gather_with_concurrency
)


def validate_content_element_class():
    """
    Validate that the ContentElement class has the expected structure.
    This helps identify attribute mismatches before they cause runtime errors.
    """
    from app.chat.types import ContentElement, ContentType, ContentMetadata
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Create proper metadata with pdf_id set
        metadata = ContentMetadata(
            pdf_id="test_pdf",
            page_number=1,
            content_type=ContentType.TEXT
        )

        # Create a test instance
        test_element = ContentElement(
            element_id="test",
            content="Test content",
            content_type=ContentType.TEXT,
            pdf_id="test_pdf",
            metadata=metadata  # Use properly initialized metadata
        )

        # Check required attributes
        required_attrs = [
            'element_id', 'content', 'content_type', 'pdf_id', 'metadata'
        ]

        for attr in required_attrs:
            if not hasattr(test_element, attr):
                logger.error(f"ContentElement class missing required attribute: {attr}")
                return False

        # Verify metadata.pdf_id is set
        if not hasattr(test_element.metadata, 'pdf_id') or not test_element.metadata.pdf_id:
            logger.error("ContentElement.metadata.pdf_id is not set")
            return False

        # Verify content_type is an enum or has expected structure
        if hasattr(test_element.content_type, 'value'):
            logger.info(f"content_type has value attribute: {test_element.content_type.value}")
        else:
            logger.warning(f"content_type has no 'value' attribute: {type(test_element.content_type)}")

        logger.info("ContentElement class validated successfully")
        return True

    except Exception as e:
        logger.error(f"Error validating ContentElement class: {str(e)}", exc_info=True)
        return False
