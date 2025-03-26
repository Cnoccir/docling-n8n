"""
Unified retrieval interface coordinating MongoDB and Qdrant stores.
Provides seamless access to document metadata and vector embeddings.
"""

import logging
import os
from typing import List, Dict, Any, Optional, Union, Set
from datetime import datetime
import uuid

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from vector_stores.mongo_store import get_mongo_store
from vector_stores.qdrant_store import get_qdrant_store
from document_processor.base_types import ContentType, ContentElement, ChunkLevel, EmbeddingType

logger = logging.getLogger(__name__)

class UnifiedVectorStore:
    """
    Unified interface for MongoDB and Qdrant coordination.
    Provides central access point for all document operations.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        """Implement singleton pattern for connection management"""
        if cls._instance is None:
            cls._instance = super(UnifiedVectorStore, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        embedding_dimension: int = 1536,
        embedding_model: str = "text-embedding-3-small"
    ):
        # Skip initialization if already done (singleton pattern)
        if self._initialized:
            return

        # Embedding settings
        self.embedding_dimension = embedding_dimension
        self.embedding_model = embedding_model

        # Initialize MongoDB and Qdrant stores
        self.mongo_store = get_mongo_store()
        self.qdrant_store = get_qdrant_store()

        # Track initialization state
        self._initialized = self.mongo_store._initialized and self.qdrant_store._initialized

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

        logger.info(f"Unified Vector Store initialized with {self.embedding_dimension} dimensions")

    def initialize(self) -> bool:
        """Initialize both MongoDB and Qdrant stores with improved error handling."""
        # Skip if already completely initialized
        if self._initialized and self.mongo_store._initialized and self.qdrant_store._initialized:
            logger.info("Vector stores already fully initialized")
            return True

        # Reset initialization metrics
        mongo_success = False
        qdrant_success = False
        error_messages = []

        # Try initializing MongoDB
        try:
            if not self.mongo_store._initialized:
                logger.info("Initializing MongoDB store...")
                mongo_success = self.mongo_store.initialize()

                if not mongo_success:
                    error_msg = f"MongoDB initialization failed: {self.mongo_store.error if hasattr(self.mongo_store, 'error') else 'Unknown error'}"
                    logger.error(error_msg)
                    error_messages.append(error_msg)
            else:
                logger.info("MongoDB store already initialized")
                mongo_success = True
        except Exception as e:
            error_msg = f"MongoDB initialization error: {str(e)}"
            logger.error(error_msg)
            error_messages.append(error_msg)

        # Try initializing Qdrant
        try:
            if not self.qdrant_store._initialized:
                logger.info("Initializing Qdrant store...")
                qdrant_success = self.qdrant_store.initialize()

                if not qdrant_success:
                    error_msg = f"Qdrant initialization failed: {self.qdrant_store.error if hasattr(self.qdrant_store, 'error') else 'Unknown error'}"
                    logger.error(error_msg)
                    error_messages.append(error_msg)
            else:
                logger.info("Qdrant store already initialized")
                qdrant_success = True
        except Exception as e:
            error_msg = f"Qdrant initialization error: {str(e)}"
            logger.error(error_msg)
            error_messages.append(error_msg)

        # CRITICAL FIX: Allow partial initialization
        # Consider initialized if at least one store is available
        self._initialized = mongo_success or qdrant_success

        # Log detailed status
        status_message = f"Vector stores initialization: MongoDB={mongo_success}, Qdrant={qdrant_success}, overall={self._initialized}"
        if self._initialized:
            logger.info(status_message)
        else:
            logger.error(f"{status_message}. Errors: {'; '.join(error_messages)}")

        return self._initialized

    def create_document_node(
        self,
        pdf_id: str,
        title: str = "Untitled Document",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Create a document entry in the metadata store."""
        # Forward to MongoDB store
        return self.mongo_store.create_document_node(pdf_id, title, metadata)

    def add_content_element(
        self,
        element: Union[ContentElement, Dict[str, Any]],
        pdf_id: str
    ) -> bool:
        """Add content element to both MongoDB and Qdrant."""
        if not self._initialized:
            if not self.initialize():
                return False

        try:
            # Add to MongoDB
            mongo_success = self.mongo_store.add_content_element(element, pdf_id)

            # Convert element for Qdrant if needed
            if hasattr(element, "dict") and callable(getattr(element, "dict")):
                qdrant_element = element.dict()
            elif isinstance(element, dict):
                qdrant_element = element
            else:
                # Create element dictionary
                qdrant_element = {
                    "element_id": getattr(element, "element_id", f"elem_{pdf_id}_{uuid.uuid4()}"),
                    "content": getattr(element, "content", ""),
                    "content_type": str(getattr(element, "content_type", "")),
                    "pdf_id": pdf_id,
                    "page": getattr(element, "page", 0)
                }

                # Get metadata
                if hasattr(element, "metadata"):
                    # Handle different metadata formats
                    if hasattr(element.metadata, "dict") and callable(getattr(element.metadata, "dict")):
                        qdrant_element.update(element.metadata.dict())
                    elif isinstance(element.metadata, dict):
                        qdrant_element.update(element.metadata)

            # Ensure content is good for embedding
            if not qdrant_element.get("content"):
                logger.warning(f"Empty content for element {qdrant_element.get('element_id')}, skipping Qdrant storage")
                return mongo_success

            # Add to Qdrant
            qdrant_success = len(self.qdrant_store.add_elements([qdrant_element])) > 0

            # Return combined success
            return mongo_success and qdrant_success

        except Exception as e:
            logger.error(f"Error adding content element: {str(e)}")
            return False

    def add_concept(
        self,
        concept_name: str,
        pdf_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Add a concept to MongoDB."""
        # Forward to MongoDB store
        return self.mongo_store.add_concept(concept_name, pdf_id, metadata)

    def add_concept_relationship(
        self,
        source: str,
        target: str,
        rel_type: str,
        pdf_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Add relationship between concepts to MongoDB."""
        # Forward to MongoDB store
        return self.mongo_store.add_concept_relationship(source, target, rel_type, pdf_id, metadata)

    def add_section_concept_relation(
        self,
        section: str,
        concept: str,
        pdf_id: str
    ) -> bool:
        """Add section-concept relationship to MongoDB."""
        # Forward to MongoDB store
        return self.mongo_store.add_section_concept_relation(section, concept, pdf_id)

    def add_procedure(self, procedure: Dict[str, Any], pdf_id: str) -> bool:
        """Add a procedure to MongoDB."""
        try:
            # Create procedure document
            procedure_doc = {
                "procedure_id": procedure.get("procedure_id", f"proc_{pdf_id}_{uuid.uuid4().hex[:8]}"),
                "pdf_id": pdf_id,
                "title": procedure.get("title", "Untitled Procedure"),
                "content": procedure.get("content", ""),
                "page": procedure.get("page", 0),
                "steps": procedure.get("steps", []),
                "parameters": procedure.get("parameters", []),
                "section_headers": procedure.get("section_headers", []),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }

            # Check if mongo_store exists, has db attribute, and db is not None
            if not hasattr(self, "mongo_store"):
                logger.error("mongo_store attribute not found")
                return False

            if self.mongo_store is None:
                logger.error("mongo_store is None")
                return False

            if not hasattr(self.mongo_store, "db"):
                logger.error("mongo_store.db attribute not found")
                return False

            if self.mongo_store.db is None:
                logger.error("mongo_store.db is None")
                return False

            if not hasattr(self.mongo_store.db, "procedures"):
                logger.error("procedures collection not found in database")
                return False

            # Now we can safely access the procedures collection
            result = self.mongo_store.db.procedures.update_one(
                {"procedure_id": procedure_doc["procedure_id"]},
                {"$set": procedure_doc},
                upsert=True
            )
            return result.acknowledged
        except Exception as e:
            logger.error(f"Error adding procedure: {str(e)}")
            return False

    def add_parameter(self, parameter: Dict[str, Any], pdf_id: str) -> bool:
        """Add a parameter to MongoDB."""
        try:
            # Create parameter document
            parameter_doc = {
                "parameter_id": parameter.get("parameter_id", f"param_{pdf_id}_{uuid.uuid4().hex[:8]}"),
                "pdf_id": pdf_id,
                "name": parameter.get("name", ""),
                "value": parameter.get("value", ""),
                "type": parameter.get("type", ""),
                "description": parameter.get("description", ""),
                "procedure_id": parameter.get("procedure_id", None),
                "section_headers": parameter.get("section_headers", []),
                "page": parameter.get("page", 0),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }

            # Check if mongo_store exists, has db attribute, and db is not None
            if not hasattr(self, "mongo_store"):
                logger.error("mongo_store attribute not found")
                return False

            if self.mongo_store is None:
                logger.error("mongo_store is None")
                return False

            if not hasattr(self.mongo_store, "db"):
                logger.error("mongo_store.db attribute not found")
                return False

            if self.mongo_store.db is None:
                logger.error("mongo_store.db is None")
                return False

            if not hasattr(self.mongo_store.db, "parameters"):
                logger.error("parameters collection not found in database")
                return False

            # Now we can safely access the parameters collection
            result = self.mongo_store.db.parameters.update_one(
                {"parameter_id": parameter_doc["parameter_id"]},
                {"$set": parameter_doc},
                upsert=True
            )
            return result.acknowledged
        except Exception as e:
            logger.error(f"Error adding parameter: {str(e)}")
            return False

    def semantic_search(
        self,
        query: str,
        k: int = 10,
        pdf_id: Optional[str] = None,
        content_types: Optional[List[str]] = None,
        chunk_level: Optional[ChunkLevel] = None,
        embedding_type: Optional[EmbeddingType] = None
    ) -> List[Document]:
        """
        Perform semantic search using vector similarity.

        Args:
            query: Query text
            k: Number of results to return
            pdf_id: Optional PDF ID to filter by
            content_types: Optional list of content types to filter by
            chunk_level: Optional chunk level to filter by
            embedding_type: Optional embedding type to filter by

        Returns:
            List of document results
        """
        if not self._initialized:
            if not self.initialize():
                return []

        # Build filter dictionary
        filter_dict = {}

        if pdf_id:
            filter_dict["pdf_id"] = pdf_id

        if content_types:
            filter_dict["content_type"] = content_types

        if chunk_level:
            filter_dict["chunk_level"] = str(chunk_level)

        if embedding_type:
            filter_dict["embedding_type"] = str(embedding_type)

        try:
            # Log the filter being used
            logger.debug(f"Semantic search filter: {filter_dict}")

            # Execute search with proper filter format
            start_time = datetime.utcnow()
            results = self.qdrant_store.similarity_search(
                query=query,
                k=k,
                filter_dict=filter_dict
            )

            # Handle empty results
            if not results:
                logger.info(f"No results found for query: {query[:50]}...")
                # Try fallback to keyword search if no results
                if len(query.split()) > 1:  # Only try keyword search for multi-word queries
                    logger.info(f"Trying keyword search fallback for: {query[:50]}...")
                    keyword_results = self.mongo_store.keyword_search(
                        query=query,
                        pdf_id=pdf_id,
                        content_types=content_types,
                        limit=k
                    )

                    # Convert to Document objects
                    if keyword_results:
                        logger.info(f"Found {len(keyword_results)} results from keyword search fallback")
                        return [
                            Document(
                                page_content=result.get("content", ""),
                                metadata={
                                    **{k: v for k, v in result.items() if k != "content"},
                                    "source": "keyword_search"
                                }
                            )
                            for result in keyword_results
                        ]

            # Update metrics
            self.metrics["queries"] += 1
            query_time = (datetime.utcnow() - start_time).total_seconds()
            self.metrics["total_query_time"] += query_time
            self.metrics["avg_query_time"] = self.metrics["total_query_time"] / self.metrics["queries"]

            # Enhance results with document metadata if available
            enhanced_results = []
            for doc in results:
                doc_id = doc.metadata.get("pdf_id")
                if doc_id:
                    # Try to get document metadata
                    doc_metadata = self.mongo_store.get_document(doc_id)
                    if doc_metadata:
                        # Add document title if available
                        if "title" in doc_metadata and "document_title" not in doc.metadata:
                            doc.metadata["document_title"] = doc_metadata["title"]

                enhanced_results.append(doc)

            logger.info(f"Semantic search completed in {query_time:.2f}s, found {len(enhanced_results)} results")
            return enhanced_results
        except Exception as e:
            logger.error(f"Error in semantic search: {str(e)}", exc_info=True)
            self.metrics["errors"] += 1
            return []

    def keyword_search(
        self,
        query: str,
        k: int = 10,
        pdf_id: Optional[str] = None,
        content_types: Optional[List[str]] = None
    ) -> List[Document]:
        """Perform keyword search using standard index matching."""
        if not self._initialized:
            if not self.initialize():
                return []

        # Use MongoDB for keyword search
        search_results = self.mongo_store.keyword_search(
            query=query,
            pdf_id=pdf_id,
            content_types=content_types,
            limit=k
        )

        # Convert to Document objects
        documents = []
        for result in search_results:
            metadata = result.copy()
            content = metadata.pop("content", "")

            doc = Document(
                page_content=content,
                metadata=metadata
            )
            documents.append(doc)

        return documents

    def hybrid_search(
        self,
        query: str,
        k: int = 10,
        pdf_ids: Optional[List[str]] = None,
        content_types: Optional[List[str]] = None,
        chunk_level: Optional[ChunkLevel] = None,
        embedding_type: Optional[EmbeddingType] = None
    ) -> List[Document]:
        """
        Perform hybrid search combining semantic and keyword search.

        Args:
            query: Query text
            k: Number of results to return
            pdf_ids: Optional list of PDF IDs to query
            content_types: Optional list of content types to filter by
            chunk_level: Optional chunk level to filter by
            embedding_type: Optional embedding type to filter by

        Returns:
            Combined list of document results
        """
        if not self._initialized:
            if not self.initialize():
                return []

        try:
            # Handle multiple PDF IDs for research mode
            all_results = []

            # If no PDF IDs provided, use None for unrestricted search
            if not pdf_ids:
                pdf_ids = [None]

            # Process each PDF ID
            for pdf_id in pdf_ids:
                # Skip None values if we have valid PDF IDs
                if pdf_id is None and len(pdf_ids) > 1:
                    continue

                # Perform semantic search
                semantic_results = self.semantic_search(
                    query=query,
                    k=k,
                    pdf_id=pdf_id,
                    content_types=content_types,
                    chunk_level=chunk_level,
                    embedding_type=embedding_type
                )

                # Perform keyword search
                keyword_results = self.keyword_search(
                    query=query,
                    k=k//2,  # Use fewer keyword results
                    pdf_id=pdf_id,
                    content_types=content_types
                )

                # Combine results for this PDF ID
                pdf_results = self._combine_search_results(
                    semantic_results,
                    keyword_results,
                    k
                )

                all_results.extend(pdf_results)

            # If we have multiple PDFs, sort by overall score
            if len(pdf_ids) > 1 and pdf_ids[0] is not None:
                all_results.sort(
                    key=lambda x: x.metadata.get("score", 0),
                    reverse=True
                )

            # If we still have no results, try a broader search
            if not all_results and pdf_ids[0] is not None:
                logger.info("No results found for specific PDFs, trying broader search")
                return self.hybrid_search(
                    query=query,
                    k=k,
                    pdf_ids=[None],  # Search across all documents
                    content_types=content_types,
                    chunk_level=chunk_level,
                    embedding_type=embedding_type
                )

            # Limit to top k results
            return all_results[:k]

        except Exception as e:
            logger.error(f"Error in hybrid search: {str(e)}", exc_info=True)
            return []

    def _combine_search_results(
        self,
        semantic_results: List[Document],
        keyword_results: List[Document],
        k: int
    ) -> List[Document]:
        """Combine semantic and keyword search results with scoring."""
        combined_results = {}

        # Add semantic results
        for doc in semantic_results:
            doc_id = doc.metadata.get("element_id")
            if not doc_id:
                continue

            combined_results[doc_id] = {
                "doc": doc,
                "semantic_score": doc.metadata.get("score", 0.0),
                "keyword_score": 0.0
            }

        # Add keyword results
        for doc in keyword_results:
            doc_id = doc.metadata.get("element_id")
            if not doc_id:
                continue

            if doc_id in combined_results:
                combined_results[doc_id]["keyword_score"] = doc.metadata.get("score", 0.0)
            else:
                combined_results[doc_id] = {
                    "doc": doc,
                    "semantic_score": 0.0,
                    "keyword_score": doc.metadata.get("score", 0.0)
                }

        # Calculate combined scores
        for doc_id, data in combined_results.items():
            combined_score = (data["semantic_score"] * 0.7) + (data["keyword_score"] * 0.3)
            data["combined_score"] = combined_score
            data["doc"].metadata["score"] = combined_score

        # Sort by combined score
        sorted_results = sorted(
            combined_results.values(),
            key=lambda x: x["combined_score"],
            reverse=True
        )

        # Return top k results
        return [data["doc"] for data in sorted_results[:k]]

    def get_document_metadata(self, pdf_id: str) -> Optional[Dict[str, Any]]:
        """Get document metadata from MongoDB."""
        if not self._initialized:
            if not self.initialize():
                return None

        return self.mongo_store.get_document(pdf_id)

    def get_procedures_by_pdf_id(
        self,
        pdf_id: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get procedures for a specific PDF ID."""
        if not self._initialized:
            if not self.initialize():
                return []

        try:
            if hasattr(self.mongo_store, "db") and self.mongo_store.db:
                procedures = list(
                    self.mongo_store.db.procedures.find(
                        {"pdf_id": pdf_id}
                    ).limit(limit)
                )
                return procedures
            return []
        except Exception as e:
            logger.error(f"Error retrieving procedures: {str(e)}")
            return []

    def get_parameters_by_pdf_id(
        self,
        pdf_id: str,
        procedure_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get parameters for a specific PDF ID and optional procedure ID."""
        if not self._initialized:
            if not self.initialize():
                return []

        try:
            query = {"pdf_id": pdf_id}
            if procedure_id:
                query["procedure_id"] = procedure_id

            if hasattr(self.mongo_store, "db") and self.mongo_store.db:
                parameters = list(
                    self.mongo_store.db.parameters.find(query).limit(limit)
                )
                return parameters
            return []
        except Exception as e:
            logger.error(f"Error retrieving parameters: {str(e)}")
            return []

    def get_concepts_by_pdf_id(
        self,
        pdf_id: str,
        is_primary: Optional[bool] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get concepts for a specific PDF ID."""
        if not self._initialized:
            if not self.initialize():
                return []

        return self.mongo_store.get_concepts_by_pdf_id(
            pdf_id=pdf_id,
            is_primary=is_primary,
            limit=limit
        )

    def find_shared_concepts(
        self,
        pdf_ids: List[str],
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Find concepts that appear in multiple documents."""
        if not self._initialized or not pdf_ids or len(pdf_ids) < 2:
            return []

        try:
            if hasattr(self.mongo_store, "db") and self.mongo_store.db:
                # Aggregate to find concepts present in multiple documents
                pipeline = [
                    {"$match": {"pdf_id": {"$in": pdf_ids}}},
                    {"$group": {
                        "_id": "$name",
                        "occurrences": {"$sum": 1},
                        "documents": {"$addToSet": "$pdf_id"},
                        "importance": {"$avg": "$importance"},
                        "is_primary": {"$max": {"$cond": ["$is_primary", 1, 0]}}
                    }},
                    {"$match": {"occurrences": {"$gt": 1}}},
                    {"$sort": {"importance": -1}},
                    {"$limit": limit}
                ]

                shared_concepts = list(
                    self.mongo_store.db.concepts.aggregate(pipeline)
                )

                # Format results
                results = []
                for concept in shared_concepts:
                    results.append({
                        "name": concept["_id"],
                        "documents": concept["documents"],
                        "document_count": len(concept["documents"]),
                        "is_primary": concept["is_primary"] > 0,
                        "importance": concept["importance"]
                    })

                return sorted(results, key=lambda x: x["document_count"], reverse=True)
            return []
        except Exception as e:
            logger.error(f"Error finding shared concepts: {str(e)}")
            return []

    def delete_document(self, pdf_id: str) -> bool:
        """Delete a document and its content from both MongoDB and Qdrant."""
        if not self._initialized:
            if not self.initialize():
                return False

        try:
            # Delete from MongoDB
            mongo_success = self.mongo_store.delete_document(pdf_id)

            # Delete from Qdrant
            qdrant_success = self.qdrant_store.delete_by_pdf_id(pdf_id)

            logger.info(f"Deleted document {pdf_id} from unified store")
            return mongo_success and qdrant_success

        except Exception as e:
            logger.error(f"Error deleting document: {str(e)}")
            return False

    def close(self) -> None:
        """Close all connections."""
        try:
            if self.mongo_store:
                self.mongo_store.close()

            if self.qdrant_store:
                self.qdrant_store.close()

            self._initialized = False
            logger.info("Unified store connections closed")

        except Exception as e:
            logger.error(f"Error closing connections: {str(e)}")

    def check_health(self) -> Dict[str, Any]:
        """
        Check health status of the vector store.

        Returns:
            Dictionary with health status information
        """
        health_info = {
            "status": "error",
            "mongo_ready": False,
            "qdrant_ready": False,
            "timestamp": datetime.utcnow().isoformat()
        }

        if not self._initialized:
            health_info["error"] = "Vector store not initialized"
            return health_info

        try:
            # Check MongoDB connection
            mongo_ready = False
            if hasattr(self, 'mongo_store') and self.mongo_store is not None:
                if hasattr(self.mongo_store, 'client') and self.mongo_store.client is not None:
                    try:
                        # Test ping
                        self.mongo_store.client.admin.command('ping')
                        mongo_ready = True

                        # Basic stats
                        health_info["mongo_status"] = {
                            "connected": True,
                            "database": self.mongo_store.db_name if hasattr(self.mongo_store, 'db_name') else "unknown"
                        }
                    except Exception as mongo_error:
                        health_info["mongo_status"] = {
                            "connected": False,
                            "error": str(mongo_error)
                        }
                else:
                    health_info["mongo_status"] = {
                        "connected": False,
                        "error": "MongoDB client not initialized"
                    }

            # Check Qdrant connection
            qdrant_ready = False
            if hasattr(self, 'qdrant_store') and self.qdrant_store is not None:
                if hasattr(self.qdrant_store, 'client') and self.qdrant_store.client is not None:
                    try:
                        # Get collection info
                        collection_info = self.qdrant_store.client.get_collection(
                            collection_name=self.qdrant_store.collection_name
                        )
                        qdrant_ready = True

                        # Basic stats
                        health_info["qdrant_status"] = {
                            "connected": True,
                            "collection": self.qdrant_store.collection_name,
                            "vectors_config": str(collection_info.config.params.vectors) if hasattr(collection_info, 'config') else "unknown"
                        }
                    except Exception as qdrant_error:
                        health_info["qdrant_status"] = {
                            "connected": False,
                            "error": str(qdrant_error)
                        }
                else:
                    health_info["qdrant_status"] = {
                        "connected": False,
                        "error": "Qdrant client not initialized"
                    }

            # Update status values
            health_info["mongo_ready"] = mongo_ready
            health_info["qdrant_ready"] = qdrant_ready

            # Overall status
            if mongo_ready and qdrant_ready:
                health_info["status"] = "ok"
            elif mongo_ready or qdrant_ready:
                health_info["status"] = "degraded"
            else:
                health_info["status"] = "error"

            # Add metrics
            health_info["metrics"] = self.metrics

            return health_info
        except Exception as e:
            health_info["error"] = str(e)
            return health_info

    async def create_document_node_async(
        self,
        pdf_id: str,
        title: str = "Untitled Document",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Async-compatible version of create_document_node.

        Args:
            pdf_id: Document identifier
            title: Document title
            metadata: Additional metadata

        Returns:
            Success status
        """
        # Call synchronous version
        return self.create_document_node(pdf_id, title, metadata)

    async def add_content_element_async(
        self,
        element: Union[ContentElement, Dict[str, Any]],
        pdf_id: str
    ) -> bool:
        """
        Async-compatible version of add_content_element.

        Args:
            element: Content element
            pdf_id: Document identifier

        Returns:
            Success status
        """
        # Call synchronous version
        return self.add_content_element(element, pdf_id)

    async def add_concept_async(
        self,
        concept_name: str,
        pdf_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Async-compatible version of add_concept.

        Args:
            concept_name: Concept name
            pdf_id: Document identifier
            metadata: Additional metadata

        Returns:
            Success status
        """
        # Call synchronous version
        return self.add_concept(concept_name, pdf_id, metadata)

    async def add_concept_relationship_async(
        self,
        source: str,
        target: str,
        rel_type: str,
        pdf_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Async-compatible version of add_concept_relationship.

        Args:
            source: Source concept
            target: Target concept
            rel_type: Relationship type
            pdf_id: Document identifier
            metadata: Additional metadata

        Returns:
            Success status
        """
        # Call synchronous version
        return self.add_concept_relationship(source, target, rel_type, pdf_id, metadata)

    async def add_section_concept_relation_async(
        self,
        section: str,
        concept: str,
        pdf_id: str
    ) -> bool:
        """
        Async-compatible version of add_section_concept_relation.

        Args:
            section: Section path or title
            concept: Concept name
            pdf_id: Document identifier

        Returns:
            Success status
        """
        # Call synchronous version
        return self.add_section_concept_relation(section, concept, pdf_id)

    async def add_procedure_async(
        self,
        procedure: Dict[str, Any],
        pdf_id: str
    ) -> bool:
        """
        Async-compatible version of add_procedure.

        Args:
            procedure: Procedure data
            pdf_id: Document identifier

        Returns:
            Success status
        """
        # Call synchronous version
        return self.add_procedure(procedure, pdf_id)

    async def add_parameter_async(
        self,
        parameter: Dict[str, Any],
        pdf_id: str
    ) -> bool:
        """
        Async-compatible version of add_parameter.

        Args:
            parameter: Parameter data
            pdf_id: Document identifier

        Returns:
            Success status
        """
        # Call synchronous version
        return self.add_parameter(parameter, pdf_id)

    async def get_document_metadata_async(self, pdf_id: str) -> Optional[Dict[str, Any]]:
        """
        Async-compatible version of get_document_metadata.

        Args:
            pdf_id: Document identifier

        Returns:
            Document metadata or None if not found
        """
        # Call synchronous version
        return self.get_document_metadata(pdf_id)

#
# UnifiedVectorStore Health Dashboard Enhancements
#

    async def get_embedding_stats(self, pdf_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get detailed embedding statistics for documents.

        Args:
            pdf_ids: Optional list of PDF IDs to check (default: all documents)

        Returns:
            Dictionary with embedding statistics
        """
        if not self._initialized:
            if not self.initialize():
                return {"error": "Vector store not initialized"}

        try:
            # Initialize statistics
            stats = {
                "total": 0,
                "documents": {},
                "content_types": {},
                "chunk_levels": {},
                "embedding_types": {}
            }

            # Get counts from Qdrant
            if hasattr(self.qdrant_store, "client") and self.qdrant_store.client:
                # First get overall collection stats
                collection_info = self.qdrant_store.client.get_collection(
                    collection_name=self.qdrant_store.collection_name
                )

                # Get total vector count
                collection_count = self.qdrant_store.client.count(
                    collection_name=self.qdrant_store.collection_name,
                    count_filter=None
                )

                stats["total"] = collection_count.count

                # If we have specific PDF IDs, get counts for each
                if pdf_ids:
                    for pdf_id in pdf_ids:
                        # Count vectors for this PDF
                        pdf_count = self.qdrant_store.client.count(
                            collection_name=self.qdrant_store.collection_name,
                            count_filter={
                                "must": [
                                    {"key": "pdf_id", "match": {"value": pdf_id}}
                                ]
                            }
                        )

                        stats["documents"][pdf_id] = pdf_count.count

                        # Get content type breakdown
                        content_types = await self._get_content_type_counts(pdf_id)
                        for content_type, count in content_types.items():
                            # Add to global content type counts
                            stats["content_types"][content_type] = stats["content_types"].get(content_type, 0) + count

                        # Get chunk level breakdown
                        chunk_levels = await self._get_chunk_level_counts(pdf_id)
                        for chunk_level, count in chunk_levels.items():
                            # Add to global chunk level counts
                            stats["chunk_levels"][chunk_level] = stats["chunk_levels"].get(chunk_level, 0) + count

                        # Get embedding type breakdown
                        embedding_types = await self._get_embedding_type_counts(pdf_id)
                        for embedding_type, count in embedding_types.items():
                            # Add to global embedding type counts
                            stats["embedding_types"][embedding_type] = stats["embedding_types"].get(embedding_type, 0) + count

            return stats

        except Exception as e:
            logger.error(f"Error getting embedding stats: {str(e)}")
            return {"error": str(e)}

    async def get_embedding_stats_for_pdf(self, pdf_id: str) -> Dict[str, Any]:
        """
        Get detailed embedding statistics for a specific PDF.

        Args:
            pdf_id: PDF ID to check

        Returns:
            Dictionary with embedding statistics for the PDF
        """
        if not self._initialized:
            if not self.initialize():
                return {"error": "Vector store not initialized"}

        try:
            # Initialize statistics
            stats = {
                "total": 0,
                "content_types": {},
                "chunk_levels": {},
                "embedding_types": {}
            }

            # Get counts from Qdrant
            if hasattr(self.qdrant_store, "client") and self.qdrant_store.client:
                # Count vectors for this PDF
                pdf_count = self.qdrant_store.client.count(
                    collection_name=self.qdrant_store.collection_name,
                    count_filter={
                        "must": [
                            {"key": "pdf_id", "match": {"value": pdf_id}}
                        ]
                    }
                )

                stats["total"] = pdf_count.count

                # Get content type breakdown
                stats["content_types"] = await self._get_content_type_counts(pdf_id)

                # Get chunk level breakdown
                stats["chunk_levels"] = await self._get_chunk_level_counts(pdf_id)

                # Get embedding type breakdown
                stats["embedding_types"] = await self._get_embedding_type_counts(pdf_id)

            return stats

        except Exception as e:
            logger.error(f"Error getting embedding stats for PDF {pdf_id}: {str(e)}")
            return {"error": str(e)}

    async def _get_content_type_counts(self, pdf_id: str) -> Dict[str, int]:
        """
        Get counts of embeddings by content type for a PDF.

        Args:
            pdf_id: PDF ID to check

        Returns:
            Dictionary mapping content types to counts
        """
        content_counts = {}

        try:
            # Get distinct content types for this PDF
            search_result = self.qdrant_store.client.scroll(
                collection_name=self.qdrant_store.collection_name,
                scroll_filter={
                    "must": [
                        {"key": "pdf_id", "match": {"value": pdf_id}}
                    ]
                },
                limit=100,
                with_payload=["content_type"],
                with_vectors=False
            )

            # Count occurrences of each content type
            points = search_result[0]
            for point in points:
                if point.payload and "content_type" in point.payload:
                    content_type = point.payload["content_type"]
                    content_counts[content_type] = content_counts.get(content_type, 0) + 1

        except Exception as e:
            logger.error(f"Error getting content type counts: {str(e)}")

        return content_counts

    async def _get_chunk_level_counts(self, pdf_id: str) -> Dict[str, int]:
        """
        Get counts of embeddings by chunk level for a PDF.

        Args:
            pdf_id: PDF ID to check

        Returns:
            Dictionary mapping chunk levels to counts
        """
        chunk_counts = {}

        try:
            # Get distinct chunk levels for this PDF
            search_result = self.qdrant_store.client.scroll(
                collection_name=self.qdrant_store.collection_name,
                scroll_filter={
                    "must": [
                        {"key": "pdf_id", "match": {"value": pdf_id}}
                    ]
                },
                limit=100,
                with_payload=["chunk_level"],
                with_vectors=False
            )

            # Count occurrences of each chunk level
            points = search_result[0]
            for point in points:
                if point.payload and "chunk_level" in point.payload:
                    chunk_level = point.payload["chunk_level"]
                    chunk_counts[chunk_level] = chunk_counts.get(chunk_level, 0) + 1

        except Exception as e:
            logger.error(f"Error getting chunk level counts: {str(e)}")

        return chunk_counts

    async def _get_embedding_type_counts(self, pdf_id: str) -> Dict[str, int]:
        """
        Get counts of embeddings by embedding type for a PDF.

        Args:
            pdf_id: PDF ID to check

        Returns:
            Dictionary mapping embedding types to counts
        """
        embedding_counts = {}

        try:
            # Get distinct embedding types for this PDF
            search_result = self.qdrant_store.client.scroll(
                collection_name=self.qdrant_store.collection_name,
                scroll_filter={
                    "must": [
                        {"key": "pdf_id", "match": {"value": pdf_id}}
                    ]
                },
                limit=100,
                with_payload=["embedding_type"],
                with_vectors=False
            )

            # Count occurrences of each embedding type
            points = search_result[0]
            for point in points:
                if point.payload and "embedding_type" in point.payload:
                    embedding_type = point.payload["embedding_type"]
                    embedding_counts[embedding_type] = embedding_counts.get(embedding_type, 0) + 1

        except Exception as e:
            logger.error(f"Error getting embedding type counts: {str(e)}")

        return embedding_counts

# Create an alias for backward compatibility with previous Neo4j implementation
TechDocVectorStore = UnifiedVectorStore

# Singleton instance getter
def get_vector_store() -> UnifiedVectorStore:
    """Get or create unified vector store instance."""
    return UnifiedVectorStore()
