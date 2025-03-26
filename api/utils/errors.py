"""
Custom exceptions for the chat module.
"""

class ChatError(Exception):
    """Base exception class for chat errors."""
    pass

class VectorStoreError(ChatError):
    """Exception raised for errors in the vector store."""
    pass

class DocumentProcessingError(ChatError):
    """Exception raised for errors during document processing."""
    pass

class AgentError(ChatError):
    """Exception raised for errors in the agent."""
    pass

class MemoryError(ChatError):
    """Exception raised for errors in the memory management."""
    pass

class LangGraphError(ChatError):
    """Exception raised for errors in the LangGraph components."""
    pass
