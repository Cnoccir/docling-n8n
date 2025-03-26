"""
Tokenization utilities for document processing.
"""

import logging
from typing import List, Dict, Any, Tuple
from transformers.tokenization_utils_base import PreTrainedTokenizerBase
from tiktoken import get_encoding

__all__ = [
    "OpenAITokenizerWrapper",
    "get_tokenizer"
]

logger = logging.getLogger(__name__)


class OpenAITokenizerWrapper(PreTrainedTokenizerBase):
    """
    Enhanced wrapper for OpenAI's tokenizer to make it compatible with HybridChunker.
    Includes optimizations for technical document processing.
    """

    def __init__(
        self,
        model_name: str = "cl100k_base",  # Default for text-embedding-3-small
        max_length: int = 8191,
        **kwargs
    ):
        """Initialize the tokenizer with configurability."""
        super().__init__(model_max_length=max_length, **kwargs)
        self.tokenizer = get_encoding(model_name)
        self._vocab_size = self.tokenizer.max_token_value
        self._encoding_name = model_name

        # Track usage for metrics
        self.tokens_processed = 0
        self.calls = 0

    def encode(self, text, add_special_tokens=False, **kwargs):
        """Encode text into token IDs."""
        encoded_ids = self.tokenizer.encode(text)
        self.tokens_processed += len(encoded_ids)
        self.calls += 1
        return encoded_ids

    def tokenize(self, text: str, **kwargs) -> List[str]:
        """
        Tokenize text while tracking usage metrics.
        Main method used by HybridChunker.
        """
        tokens = [str(t) for t in self.tokenizer.encode(text)]
        self.tokens_processed += len(tokens)
        self.calls += 1
        return tokens

    def _tokenize(self, text: str) -> List[str]:
        """Internal tokenization method."""
        return self.tokenize(text)

    def _convert_token_to_id(self, token: str) -> int:
        """Convert token to ID."""
        return int(token)

    def _convert_id_to_token(self, index: int) -> str:
        """Convert ID to token."""
        return str(index)

    def get_vocab(self) -> Dict[str, int]:
        """Get vocabulary mapping."""
        return dict(enumerate(range(self.vocab_size)))

    def estimate_tokens(self, text: str) -> int:
        """Efficiently estimate token count without full tokenization."""
        # For quick estimation, we use a character-based heuristic
        # This is much faster than full tokenization for estimation purposes
        char_count = len(text)
        # Typical ratios for English text in cl100k:
        # ~4 characters per token for normal text
        # ~3 characters per token for code

        # Check if text looks like code
        if '```' in text or '{' in text or 'def ' in text or 'function ' in text:
            return char_count // 3
        else:
            return char_count // 4

    def count_tokens_exact(self, text: str) -> int:
        """Count tokens with exact tokenization."""
        return len(self.tokenizer.encode(text))

    @property
    def vocab_size(self) -> int:
        """Get vocabulary size."""
        return self._vocab_size

    def save_vocabulary(self, *args) -> Tuple[str]:
        """Save vocabulary (required by HF interface)."""
        return ()

    def get_metrics(self) -> Dict[str, Any]:
        """Get tokenizer usage metrics."""
        return {
            "tokens_processed": self.tokens_processed,
            "calls": self.calls,
            "average_tokens_per_call": self.tokens_processed / max(1, self.calls),
            "model_name": self._encoding_name
        }

    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        """Class method to match HuggingFace's interface."""
        return cls()


def get_tokenizer(model_name: str, **kwargs) -> PreTrainedTokenizerBase:
    """
    Get appropriate tokenizer for document processing.
    Optimized for technical documents with enhanced metadata.
    """
    if model_name.startswith(("text-embedding-", "gpt-")):
        return OpenAITokenizerWrapper(model_name="cl100k_base", **kwargs)
    else:
        from transformers import AutoTokenizer
        return AutoTokenizer.from_pretrained(model_name, **kwargs)
