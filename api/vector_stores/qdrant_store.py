"""
Qdrant vector store for embedding storage and similarity search.
Optimized for technical document retrieval.
"""

import logging
import os
import json
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)

class QdrantStore:
    """Qdrant vector store for embedding storage and retrieval."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        """Implement singleton pattern for connection management"""
        if cls._instance is None:
            cls._instance = super(QdrantStore, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        url: str = None,
        port: int = None,
        collection_name: str = "content_vectors",
        embedding_dimension: int = 1536,
        embedding_model: str = "text-embedding-3-small"
    ):
        # Skip initialization if already done (singleton pattern)
        if self._initialized:
            return

        # Use parameters or environment variables
        self.url = url or os.environ.get("QDRANT_HOST", "localhost")
        self.port = port or int(os.environ.get("QDRANT_PORT", "6333"))
        self.collection_name = collection_name
        self.embedding_dimension = embedding_dimension
        self.embedding_model = embedding_model

        # Track initialization state
        self._initialized = False
        self.client = None
        self.error = None

        # Initialize embeddings
        self.embeddings = OpenAIEmbeddings(
            model=self.embedding_model,
            openai_api_key=os.environ.get("OPENAI_API_KEY")
        )

        # Initialize metrics
        self.metrics = {
            "queries": 0,
            "errors": 0,
            "avg_query_time": 0,
            "total_query_time": 0
        }

        # Initialize connection
        self.initialize()

        logger.info(f"Qdrant Vector Store initialized with {self.embedding_dimension} dimensions")

    def initialize(self) -> bool:
        """
        Initialize the Qdrant connection and collection.
        Returns: Success status
        """
        if self._initialized and self.client:
            return True

        try:
            # Create client
            self.client = QdrantClient(
                host=self.url,
                port=self.port,
                timeout=10.0  # 10-second timeout
            )

            # Check if collection exists
            collections = self.client.get_collections().collections
            collection_names = [collection.name for collection in collections]

            # Create collection if it doesn't exist
            if self.collection_name not in collection_names:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.embedding_dimension,
                        distance=models.Distance.COSINE
                    )
                )

                # Create payload indexes for filtering
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="pdf_id",
                    field_schema=models.PayloadSchemaType.KEYWORD
                )

                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="content_type",
                    field_schema=models.PayloadSchemaType.KEYWORD
                )

                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="element_id",
                    field_schema=models.PayloadSchemaType.KEYWORD
                )

                logger.info(f"Created Qdrant collection: {self.collection_name}")

            self._initialized = True
            logger.info("Qdrant connection and collection initialized successfully")
            return True

        except Exception as e:
            self.error = str(e)
            logger.error(f"Failed to initialize Qdrant: {str(e)}")
            self._initialized = False
            return False

    def add_texts(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        element_ids: Optional[List[str]] = None,
        batch_size: int = 100
    ) -> List[str]:
        """
        Add texts to Qdrant vector store.

        Args:
            texts: List of text content
            metadatas: Optional list of metadata dictionaries
            element_ids: Optional list of element IDs (generated if not provided)
            batch_size: Batch size for adding vectors

        Returns:
            List of element IDs
        """
        if not self._initialized:
            if not self.initialize():
                return []

        if not texts:
            return []

        try:
            # Generate embeddings
            embeddings = self.embeddings.embed_documents(texts)

            # Generate IDs if not provided
            if not element_ids:
                element_ids = [str(uuid.uuid4()) for _ in range(len(texts))]

            # Use empty metadata if not provided
            if not metadatas:
                metadatas = [{} for _ in range(len(texts))]

            # Ensure lists have the same length
            if len(texts) != len(embeddings) or len(texts) != len(metadatas) or len(texts) != len(element_ids):
                raise ValueError("texts, embeddings, metadatas, and element_ids must have the same length")

            # Prepare points for batched insertion
            points = []
            original_to_uuid_map = {}  # Map to track original IDs to UUID conversions

            for i, (text, embedding, metadata, element_id) in enumerate(zip(texts, embeddings, metadatas, element_ids)):
                # Clean metadata for Qdrant
                clean_metadata = {k: v for k, v in metadata.items() if v is not None}

                # Ensure required fields are present
                if "content" not in clean_metadata:
                    clean_metadata["content"] = text
                if "element_id" not in clean_metadata:
                    clean_metadata["element_id"] = element_id

                # Store original ID for reference and retrieval
                clean_metadata["original_id"] = element_id

                # Convert element_id to UUID format accepted by Qdrant
                try:
                    # Try using it as-is if it's already a UUID
                    try:
                        # This will raise ValueError if not a valid UUID
                        uuid_obj = uuid.UUID(str(element_id))
                        uuid_id = str(uuid_obj)
                    except ValueError:
                        # Create a deterministic UUID from the string ID
                        uuid_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(element_id)))

                    # Keep track of the mapping
                    original_to_uuid_map[element_id] = uuid_id
                except Exception:
                    # Fallback to random UUID if all else fails
                    uuid_id = str(uuid.uuid4())
                    original_to_uuid_map[element_id] = uuid_id

                # Create point with UUID as ID
                point = models.PointStruct(
                    id=uuid_id,  # Use UUID format for Qdrant
                    vector=embedding,
                    payload=clean_metadata
                )

                points.append(point)

            # Insert in batches
            successful_ids = []
            for i in range(0, len(points), batch_size):
                batch = points[i:i+batch_size]
                try:
                    self.client.upsert(
                        collection_name=self.collection_name,
                        points=batch
                    )
                    # Track successful insertions using original IDs
                    for point in batch:
                        original_id = point.payload.get("original_id")
                        if original_id:
                            successful_ids.append(original_id)
                except Exception as batch_error:
                    logger.error(f"Error in batch {i//batch_size}: {str(batch_error)}")
                    # Continue with next batch

            logger.info(f"Added {len(successful_ids)}/{len(texts)} texts to Qdrant")
            return successful_ids

        except Exception as e:
            logger.error(f"Error adding texts to Qdrant: {str(e)}")
            return []

    def add_elements(
        self,
        elements: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> List[str]:
        """
        Add content elements to Qdrant vector store.

        Args:
            elements: List of content element dictionaries
            batch_size: Batch size for adding vectors

        Returns:
            List of element IDs
        """
        if not self._initialized:
            if not self.initialize():
                return []

        if not elements:
            return []

        try:
            # Extract texts and metadata
            texts = []
            metadatas = []
            element_ids = []

            for element in elements:
                # Get content
                content = element.get("content", "")
                if not content:
                    continue

                # Get element ID
                element_id = element.get("element_id", str(uuid.uuid4()))

                # Prepare metadata
                metadata = {}

                # Copy all metadata fields
                metadata.update(element)

                # Remove content from metadata to avoid duplication
                if "content" in metadata:
                    del metadata["content"]

                texts.append(content)
                metadatas.append(metadata)
                element_ids.append(element_id)

            # Add texts to vector store
            return self.add_texts(texts, metadatas, element_ids, batch_size)

        except Exception as e:
            logger.error(f"Error adding elements to Qdrant: {str(e)}")
            return []

    def similarity_search(
        self,
        query: str,
        k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Document]:
        """
        Perform similarity search using vector embeddings.

        Args:
            query: Query text
            k: Number of results to return
            filter_dict: Optional filter dictionary
            **kwargs: Additional arguments

        Returns:
            List of document results
        """
        if not self._initialized:
            if not self.initialize():
                return []

        start_time = datetime.utcnow()

        try:
            # Generate query embedding
            query_embedding = self.embeddings.embed_query(query)

            # Convert filter_dict to Qdrant filter
            filter_condition = None
            if filter_dict:
                conditions = []
                for key, value in filter_dict.items():
                    if isinstance(value, list):
                        # For list values, use MatchAny for OR logic
                        string_values = [str(v) for v in value]  # Convert all values to strings
                        conditions.append(
                            models.FieldCondition(
                                key=key,
                                match=models.MatchAny(any=string_values)
                            )
                        )
                    else:
                        # For single values, use MatchValue
                        conditions.append(
                            models.FieldCondition(
                                key=key,
                                match=models.MatchValue(value=str(value))  # Convert value to string
                            )
                        )

                if conditions:
                    filter_condition = models.Filter(
                        must=conditions
                    )

            # Log the actual filter being sent to Qdrant
            logger.debug(f"Qdrant search filter: {filter_condition}")

            # Execute search
            # FIXED: Pass the filter using filter_selector parameter, not filter parameter
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=k,
                with_payload=True,
                # Changed from filter=filter_condition to using query_filter
                query_filter=filter_condition  # This is the correct parameter name
            )

            # Convert to Document objects
            documents = []
            for point in search_result:
                metadata = point.payload.copy() if point.payload else {}

                # Add score to metadata
                metadata["score"] = point.score

                # Use original_id if available for consistency
                if "original_id" in metadata:
                    metadata["element_id"] = metadata["original_id"]

                # Ensure content is available
                content = metadata.pop("content", "")
                if not content and "content" in point.payload:
                    content = point.payload["content"]

                # Create document
                doc = Document(
                    page_content=content,
                    metadata=metadata
                )

                documents.append(doc)

            # Update metrics
            self.metrics["queries"] += 1
            query_time = (datetime.utcnow() - start_time).total_seconds()
            self.metrics["total_query_time"] += query_time
            self.metrics["avg_query_time"] = self.metrics["total_query_time"] / self.metrics["queries"]

            logger.info(f"Similarity search completed in {query_time:.2f}s, found {len(documents)} results")
            return documents

        except Exception as e:
            logger.error(f"Error in similarity search: {str(e)}", exc_info=True)
            self.metrics["errors"] += 1
            return []

    def delete_by_pdf_id(self, pdf_id: str) -> bool:
        """
        Delete all vectors for a specific PDF ID.

        Args:
            pdf_id: PDF ID

        Returns:
            Success status
        """
        if not self._initialized:
            if not self.initialize():
                return False

        try:
            # Create filter
            filter_condition = models.Filter(
                must=[
                    models.FieldCondition(
                        key="pdf_id",
                        match=models.MatchValue(value=pdf_id)
                    )
                ]
            )

            # Delete points
            result = self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=filter_condition
                )
            )

            logger.info(f"Deleted vectors for PDF {pdf_id} from Qdrant")
            return True

        except Exception as e:
            logger.error(f"Error deleting vectors from Qdrant: {str(e)}")
            return False

    def close(self) -> None:
        """Close Qdrant connection"""
        # Qdrant HTTP client doesn't need explicit closing
        self._initialized = False
        logger.info("Qdrant connection closed")

    async def check_health(self) -> Dict[str, Any]:
        """
        Check Qdrant health and connectivity.

        Returns:
            Dictionary with health status information
        """
        health_info = {
            "status": "error",
            "connection": "failed",
            "database_ready": False,
            "timestamp": datetime.utcnow().isoformat()
        }

        if not self.client or not self._initialized:
            health_info["error"] = "Qdrant client not initialized"
            return health_info

        try:
            # Check collection info
            collection_info = self.client.get_collection(self.collection_name)

            # Check vector count
            collection_count = self.client.count(
                collection_name=self.collection_name,
                count_filter=None
            )

            # Get info
            health_info.update({
                "connection": "connected",
                "status": "ok",
                "database_ready": True,
                "vector_count": collection_count.count,
                "dimension": collection_info.config.params.vectors.size,
                "collection_name": self.collection_name
            })

            return health_info

        except Exception as e:
            health_info["error"] = str(e)
            return health_info

    async def get_counts_by_filter(self, filter_dict: Dict[str, Any]) -> Dict[str, int]:
        """
        Get counts of vectors matching a filter.

        Args:
            filter_dict: Filter dictionary

        Returns:
            Dictionary with counts
        """
        if not self._initialized:
            if not self.initialize():
                return {"total": 0}

        try:
            # Convert filter_dict to Qdrant filter
            filter_condition = None
            if filter_dict:
                from qdrant_client.http import models
                conditions = []
                for key, value in filter_dict.items():
                    if isinstance(value, list):
                        conditions.append(
                            models.FieldCondition(
                                key=key,
                                match=models.MatchAny(any=value)
                            )
                        )
                    else:
                        conditions.append(
                            models.FieldCondition(
                                key=key,
                                match=models.MatchValue(value=value)
                            )
                        )

                if conditions:
                    filter_condition = models.Filter(
                        must=conditions
                    )

            # Get count
            count_result = self.client.count(
                collection_name=self.collection_name,
                count_filter=filter_condition
            )

            return {"total": count_result.count}

        except Exception as e:
            logger.error(f"Error getting counts by filter: {str(e)}")
            return {"total": 0, "error": str(e)}

# Singleton instance getter
def get_qdrant_store() -> QdrantStore:
    """Get or create Qdrant store instance"""
    return QdrantStore()
