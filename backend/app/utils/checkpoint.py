"""Processing checkpoint manager to enable resume/retry without reprocessing."""
import json
import redis
import os
from typing import Optional, Dict, Any, List
from datetime import timedelta

# Reuse the same Redis connection
redis_client = redis.from_url(
    os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    decode_responses=True
)

CHECKPOINT_TTL = 86400  # 24 hours


class ProcessingCheckpoint:
    """Manage processing checkpoints for resumable document processing."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.key = f"checkpoint:{job_id}:state"

    def save(self, state: Dict[str, Any]) -> bool:
        """
        Save checkpoint state to Redis.

        State structure:
        {
            "current_step": "processing_images",
            "progress": 45,
            "parsed_doc_json": {...},  # Entire parsed doc (avoid re-parsing)
            "summary": "...",
            "summary_tokens": 150,
            "hierarchy_built": true,
            "images_processed": [0, 1, 2, ...],  # Indices of processed images
            "images_data": {
                "0": {"s3_url": "...", "summary": "...", "tokens": 85, ...},
                "1": {...}
            },
            "tables_processed": [0, 1, ...],
            "tables_data": {
                "0": {"description": "...", "markdown": "...", ...}
            },
            "embeddings_generated": false
        }
        """
        try:
            redis_client.setex(
                self.key,
                CHECKPOINT_TTL,
                json.dumps(state)
            )
            return True
        except Exception as e:
            print(f"❌ Failed to save checkpoint: {e}")
            return False

    def load(self) -> Optional[Dict[str, Any]]:
        """Load checkpoint state from Redis."""
        try:
            data = redis_client.get(self.key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            print(f"❌ Failed to load checkpoint: {e}")
            return None

    def exists(self) -> bool:
        """Check if checkpoint exists."""
        return redis_client.exists(self.key) > 0

    def delete(self) -> bool:
        """Delete checkpoint (after successful completion)."""
        try:
            redis_client.delete(self.key)
            return True
        except Exception as e:
            print(f"❌ Failed to delete checkpoint: {e}")
            return False

    def update_progress(self, current_step: str, progress: int, **kwargs) -> bool:
        """Update progress within checkpoint."""
        state = self.load() or {}
        state['current_step'] = current_step
        state['progress'] = progress
        state.update(kwargs)
        return self.save(state)

    # Helper methods for specific checkpoints

    def save_parsed_doc(self, doc_json: Dict[str, Any]) -> bool:
        """Save parsed document to avoid re-parsing."""
        state = self.load() or {}
        state['parsed_doc_json'] = doc_json
        state['parsed'] = True
        return self.save(state)

    def get_parsed_doc(self) -> Optional[Dict[str, Any]]:
        """Get cached parsed document."""
        state = self.load()
        if state and state.get('parsed'):
            return state.get('parsed_doc_json')
        return None

    def save_summary(self, summary: str, tokens: int) -> bool:
        """Save document summary."""
        state = self.load() or {}
        state['summary'] = summary
        state['summary_tokens'] = tokens
        state['summary_generated'] = True
        return self.save(state)

    def get_summary(self) -> Optional[tuple[str, int]]:
        """Get cached summary."""
        state = self.load()
        if state and state.get('summary_generated'):
            return state.get('summary'), state.get('summary_tokens', 0)
        return None

    def save_hierarchy(self) -> bool:
        """Mark hierarchy as built."""
        state = self.load() or {}
        state['hierarchy_built'] = True
        return self.save(state)

    def is_hierarchy_built(self) -> bool:
        """Check if hierarchy was already built."""
        state = self.load()
        return state.get('hierarchy_built', False) if state else False

    def save_image_result(self, image_index: int, image_data: Dict[str, Any]) -> bool:
        """
        Save individual image processing result.

        Args:
            image_index: Index in the original images array
            image_data: {
                's3_url': 'https://...',
                'summary': '...',
                'image_type': 'diagram',
                'tokens': 85,
                'page_number': 1,
                'bbox': {...},
                'caption': '...'
            }
        """
        state = self.load() or {}

        # Initialize if needed
        if 'images_processed' not in state:
            state['images_processed'] = []
        if 'images_data' not in state:
            state['images_data'] = {}

        # Add to processed list
        if image_index not in state['images_processed']:
            state['images_processed'].append(image_index)

        # Save data
        state['images_data'][str(image_index)] = image_data

        return self.save(state)

    def get_processed_images(self) -> tuple[List[int], Dict[str, Any]]:
        """
        Get list of processed image indices and their data.

        Returns:
            (processed_indices, images_data_dict)
        """
        state = self.load()
        if not state:
            return [], {}

        return (
            state.get('images_processed', []),
            state.get('images_data', {})
        )

    def save_table_result(self, table_index: int, table_data: Dict[str, Any]) -> bool:
        """Save individual table processing result."""
        state = self.load() or {}

        if 'tables_processed' not in state:
            state['tables_processed'] = []
        if 'tables_data' not in state:
            state['tables_data'] = {}

        if table_index not in state['tables_processed']:
            state['tables_processed'].append(table_index)

        state['tables_data'][str(table_index)] = table_data

        return self.save(state)

    def get_processed_tables(self) -> tuple[List[int], Dict[str, Any]]:
        """Get list of processed table indices and their data."""
        state = self.load()
        if not state:
            return [], {}

        return (
            state.get('tables_processed', []),
            state.get('tables_data', {})
        )

    def save_embeddings_done(self) -> bool:
        """Mark embeddings as generated."""
        state = self.load() or {}
        state['embeddings_generated'] = True
        return self.save(state)

    def are_embeddings_done(self) -> bool:
        """Check if embeddings were generated."""
        state = self.load()
        return state.get('embeddings_generated', False) if state else False

    def get_state_summary(self) -> str:
        """Get human-readable summary of checkpoint state."""
        state = self.load()
        if not state:
            return "No checkpoint found"

        lines = []
        lines.append(f"Current Step: {state.get('current_step', 'unknown')}")
        lines.append(f"Progress: {state.get('progress', 0)}%")

        if state.get('parsed'):
            lines.append("✓ Document parsed")
        if state.get('summary_generated'):
            lines.append(f"✓ Summary generated ({state.get('summary_tokens', 0)} tokens)")
        if state.get('hierarchy_built'):
            lines.append("✓ Hierarchy built")

        images_count = len(state.get('images_processed', []))
        if images_count > 0:
            lines.append(f"✓ {images_count} images processed")

        tables_count = len(state.get('tables_processed', []))
        if tables_count > 0:
            lines.append(f"✓ {tables_count} tables processed")

        if state.get('embeddings_generated'):
            lines.append("✓ Embeddings generated")

        return "\n".join(lines)
