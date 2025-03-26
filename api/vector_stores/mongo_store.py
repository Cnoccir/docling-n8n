"""
MongoDB client for document metadata storage.
Handles document structure, elements, and relationships.
"""

import logging
import os
import json
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from pymongo import MongoClient, ASCENDING, TEXT, IndexModel
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import pymongo

from app.chat.types import ContentType, ContentElement, ContentMetadata

logger = logging.getLogger(__name__)

class MongoStore:
    """MongoDB client for document metadata and structure."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        """Implement singleton pattern for connection management"""
        if cls._instance is None:
            cls._instance = super(MongoStore, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        uri: str = None,
        db_name: str = "tech_rag",
    ):
        # Skip initialization if already done (singleton pattern)
        if self._initialized:
            return

        # Use parameters or environment variables
        self.uri = uri or os.environ.get("MONGODB_URI", "mongodb://localhost:27017/")
        self.db_name = db_name or os.environ.get("MONGODB_DB_NAME", "tech_rag")

        # Track initialization state
        self._initialized = False
        self.client = None
        self.db = None
        self.error = None

        # Initialize metrics
        self.metrics = {
            "queries": 0,
            "errors": 0,
            "avg_query_time": 0,
            "total_query_time": 0
        }

        # Initialize connection
        self.initialize()

        logger.info(f"MongoDB Store initialized with database: {self.db_name}")

    def initialize(self) -> bool:
        """
        Initialize the MongoDB connection and collections.
        Returns: Success status
        """
        if self._initialized and self.client is not None and self.db is not None:
            return True

        try:
            self.client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=5000,  # 5-second timeout
                connectTimeoutMS=5000,          # 5-second connection timeout
                socketTimeoutMS=10000,          # 10-second socket timeout
                maxPoolSize=100,                # Connection pool size
                retryWrites=True                # Retry writes on failure
            )

            # Verify connection by performing a ping
            self.client.admin.command('ping')

            self.db = self.client[self.db_name]

            # Ensure collections exist
            existing_collections = self.db.list_collection_names()
            collections_to_check = ["documents", "content_elements", "concepts", "relationships"]
            for collection_name in collections_to_check:
                if collection_name not in existing_collections:
                    self.db.create_collection(collection_name)
                    logger.info(f"Created collection: {collection_name}")


            # Index creation

            # Document indexes
            self.db.documents.create_index([("pdf_id", ASCENDING)], unique=True)
            self.db.documents.create_index([("title", TEXT)])

            # Content element indexes
            self.db.content_elements.create_index([("element_id", ASCENDING)], unique=True)
            self.db.content_elements.create_index([("pdf_id", ASCENDING)])
            self.db.content_elements.create_index([("content_type", ASCENDING)])
            self.db.content_elements.create_index([("page_number", ASCENDING)])
            self.db.content_elements.create_index([("content", TEXT)])

            # Concept indexes
            self.db.concepts.create_index([
                ("name", ASCENDING),
                ("pdf_id", ASCENDING)
            ], unique=True)
            self.db.concepts.create_index([("pdf_id", ASCENDING)])
            self.db.concepts.create_index([("is_primary", ASCENDING)])

            # Relationship indexes
            self.db.relationships.create_index([
                ("source", ASCENDING),
                ("target", ASCENDING),
                ("type", ASCENDING),
                ("pdf_id", ASCENDING)
            ], unique=True)

            self._initialized = True
            logger.info("MongoDB connection and schema initialized successfully")
            return True

        except ConnectionFailure as e:
            self.error = f"MongoDB connection failure: {str(e)}"
            logger.error(self.error)
            self._initialized = False
            return False
        except ServerSelectionTimeoutError as e:
            self.error = f"MongoDB server selection timeout: {str(e)}"
            logger.error(self.error)
            self._initialized = False
            return False
        except Exception as e:
            self.error = f"MongoDB initialization error: {str(e)}"
            logger.error(self.error)

            if self.client is not None:
                self.client.close()
                self.client = None

            self._initialized = False
            return False

    def create_document_node(
        self,
        pdf_id: str,
        title: str = "Untitled Document",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Create a document entry in MongoDB.

        Args:
            pdf_id: Document ID
            title: Document title
            metadata: Additional metadata

        Returns:
            Success status
        """
        if not self._initialized:
            if not self.initialize():
                return False

        try:
            # Format metadata dictionary
            metadata_dict = metadata or {}

            # Handle complex objects in metadata
            for key, value in metadata_dict.items():
                if isinstance(value, (dict, list)):
                    metadata_dict[key] = json.dumps(value)

            # Create document object
            document = {
                "pdf_id": pdf_id,
                "title": title,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                **metadata_dict  # Include all metadata fields directly
            }

            # Use upsert to handle both insert and update
            result = self.db.documents.update_one(
                {"pdf_id": pdf_id},
                {"$set": document},
                upsert=True
            )

            success = result.acknowledged

            if success:
                logger.info(f"Document created/updated in MongoDB: {pdf_id}")
            else:
                logger.warning(f"Failed to create/update document in MongoDB: {pdf_id}")

            return success

        except Exception as e:
            logger.error(f"Error creating document in MongoDB: {str(e)}")
            return False

    def add_content_element(
        self,
        element: Union[ContentElement, Dict[str, Any]],
        pdf_id: str
    ) -> bool:
        """
        Add content element to MongoDB.

        Args:
            element: Content element object or dictionary
            pdf_id: PDF ID

        Returns:
            Success status
        """
        if not self._initialized:
            if not self.initialize():
                return False

        try:
            # Convert ContentElement to dictionary if needed
            if hasattr(element, "dict") and callable(getattr(element, "dict")):
                element_dict = element.dict()
            elif isinstance(element, dict):
                element_dict = element
            else:
                element_dict = {
                    "element_id": getattr(element, "element_id", f"elem_{pdf_id}_{datetime.utcnow().timestamp()}"),
                    "content": getattr(element, "content", ""),
                    "content_type": getattr(element, "content_type", "text"),
                    "pdf_id": pdf_id,
                    "page": getattr(element, "page", 0),
                    "metadata": {}
                }

                # Get metadata if present
                if hasattr(element, "metadata"):
                    # Handle different metadata formats
                    if hasattr(element.metadata, "dict") and callable(getattr(element.metadata, "dict")):
                        element_dict["metadata"] = element.metadata.dict()
                    elif isinstance(element.metadata, dict):
                        element_dict["metadata"] = element.metadata

            # Ensure required fields
            if "element_id" not in element_dict:
                element_dict["element_id"] = f"elem_{pdf_id}_{datetime.utcnow().timestamp()}"
            if "pdf_id" not in element_dict:
                element_dict["pdf_id"] = pdf_id

            # Clean up dictionary for MongoDB
            # Flatten some metadata for efficient querying
            metadata = element_dict.get("metadata", {})
            element_dict["content_type"] = str(element_dict.get("content_type", ""))
            element_dict["page_number"] = metadata.get("page_number", 0) if metadata else 0
            element_dict["section_headers"] = metadata.get("section_headers", []) if metadata else []
            element_dict["technical_terms"] = metadata.get("technical_terms", []) if metadata else []
            element_dict["hierarchy_level"] = metadata.get("hierarchy_level", 0) if metadata else 0

            # Set creation/update timestamps
            element_dict["created_at"] = datetime.utcnow()
            element_dict["updated_at"] = datetime.utcnow()

            # Use upsert to handle both insert and update
            result = self.db.content_elements.update_one(
                {"element_id": element_dict["element_id"]},
                {"$set": element_dict},
                upsert=True
            )

            success = result.acknowledged

            if success:
                logger.debug(f"Content element added to MongoDB: {element_dict['element_id']}")
            else:
                logger.warning(f"Failed to add content element to MongoDB: {element_dict['element_id']}")

            return success

        except Exception as e:
            logger.error(f"Error adding content element to MongoDB: {str(e)}")
            return False

    def add_concept(
        self,
        concept_name: str,
        pdf_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add a concept to MongoDB.

        Args:
            concept_name: Concept name/term
            pdf_id: PDF ID
            metadata: Concept metadata

        Returns:
            Success status
        """
        if not self._initialized:
            if not self.initialize():
                return False

        try:
            # Format metadata
            metadata_dict = metadata or {}

            # Create concept object
            concept = {
                "name": concept_name,
                "pdf_id": pdf_id,
                "is_primary": metadata_dict.get("is_primary", False),
                "importance": metadata_dict.get("importance", 0.5),
                "category": metadata_dict.get("category", None),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }

            # Use upsert to handle both insert and update
            result = self.db.concepts.update_one(
                {
                    "name": concept_name,
                    "pdf_id": pdf_id
                },
                {"$set": concept},
                upsert=True
            )

            success = result.acknowledged

            if success:
                logger.debug(f"Concept added to MongoDB: {concept_name}")
            else:
                logger.warning(f"Failed to add concept to MongoDB: {concept_name}")

            return success

        except Exception as e:
            logger.error(f"Error adding concept to MongoDB: {str(e)}")
            return False

    def add_concept_relationship(
        self,
        source: str,
        target: str,
        rel_type: str,
        pdf_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add relationship between concepts to MongoDB.

        Args:
            source: Source concept name
            target: Target concept name
            rel_type: Relationship type
            pdf_id: PDF ID
            metadata: Relationship metadata

        Returns:
            Success status
        """
        if not self._initialized:
            if not self.initialize():
                return False

        try:
            # Format metadata
            metadata_dict = metadata or {}

            # Create relationship object
            relationship = {
                "source": source,
                "target": target,
                "type": rel_type,
                "pdf_id": pdf_id,
                "weight": metadata_dict.get("weight", 0.5),
                "context": metadata_dict.get("context", ""),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }

            # Use upsert to handle both insert and update
            result = self.db.relationships.update_one(
                {
                    "source": source,
                    "target": target,
                    "type": rel_type,
                    "pdf_id": pdf_id
                },
                {"$set": relationship},
                upsert=True
            )

            success = result.acknowledged

            if success:
                logger.debug(f"Relationship added to MongoDB: {source} -> {target}")
            else:
                logger.warning(f"Failed to add relationship to MongoDB: {source} -> {target}")

            return success

        except Exception as e:
            logger.error(f"Error adding relationship to MongoDB: {str(e)}")
            return False

    def add_section_concept_relation(
        self,
        section: str,
        concept: str,
        pdf_id: str
    ) -> bool:
        """
        Add section-concept relationship to MongoDB.

        Args:
            section: Section path or title
            concept: Concept name
            pdf_id: PDF ID

        Returns:
            Success status
        """
        if not self._initialized:
            if not self.initialize():
                return False

        try:
            # Create section-concept relationship object
            relationship = {
                "source": section,
                "target": concept,
                "type": "section_contains",
                "pdf_id": pdf_id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }

            # Use upsert to handle both insert and update
            result = self.db.relationships.update_one(
                {
                    "source": section,
                    "target": concept,
                    "type": "section_contains",
                    "pdf_id": pdf_id
                },
                {"$set": relationship},
                upsert=True
            )

            success = result.acknowledged

            if success:
                logger.debug(f"Section-concept relationship added to MongoDB: {section} contains {concept}")
            else:
                logger.warning(f"Failed to add section-concept relationship to MongoDB: {section} contains {concept}")

            return success

        except Exception as e:
            logger.error(f"Error adding section-concept relationship to MongoDB: {str(e)}")
            return False

    def get_document(self, pdf_id: str) -> Optional[Dict[str, Any]]:
        """
        Get document by ID.

        Args:
            pdf_id: PDF ID

        Returns:
            Document dictionary or None if not found
        """
        if not self._initialized:
            if not self.initialize():
                return None

        try:
            document = self.db.documents.find_one({"pdf_id": pdf_id})
            return document

        except Exception as e:
            logger.error(f"Error getting document from MongoDB: {str(e)}")
            return None

    def get_elements_by_pdf_id(
        self,
        pdf_id: str,
        content_types: Optional[List[str]] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Get content elements by PDF ID.

        Args:
            pdf_id: PDF ID
            content_types: Optional list of content types to filter by
            limit: Maximum number of elements to return

        Returns:
            List of content element dictionaries
        """
        if not self._initialized:
            if not self.initialize():
                return []

        try:
            # Build query
            query = {"pdf_id": pdf_id}

            # Add content type filter if specified
            if content_types:
                query["content_type"] = {"$in": content_types}

            # Execute query
            elements = list(
                self.db.content_elements.find(query)
                .sort("page_number", pymongo.ASCENDING)
                .limit(limit)
            )

            return elements

        except Exception as e:
            logger.error(f"Error getting content elements from MongoDB: {str(e)}")
            return []

    def get_concepts_by_pdf_id(
        self,
        pdf_id: str,
        is_primary: Optional[bool] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get concepts by PDF ID.

        Args:
            pdf_id: PDF ID
            is_primary: Optional filter for primary concepts
            limit: Maximum number of concepts to return

        Returns:
            List of concept dictionaries
        """
        if not self._initialized:
            if not self.initialize():
                return []

        try:
            # Build query
            query = {"pdf_id": pdf_id}

            # Add primary filter if specified
            if is_primary is not None:
                query["is_primary"] = is_primary

            # Execute query
            concepts = list(
                self.db.concepts.find(query)
                .sort("importance", pymongo.DESCENDING)
                .limit(limit)
            )

            return concepts

        except Exception as e:
            logger.error(f"Error getting concepts from MongoDB: {str(e)}")
            return []

    def get_relationships_by_pdf_id(
        self,
        pdf_id: str,
        rel_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get relationships by PDF ID.

        Args:
            pdf_id: PDF ID
            rel_type: Optional filter for relationship type
            limit: Maximum number of relationships to return

        Returns:
            List of relationship dictionaries
        """
        if not self._initialized:
            if not self.initialize():
                return []

        try:
            # Build query
            query = {"pdf_id": pdf_id}

            # Add relationship type filter if specified
            if rel_type:
                query["type"] = rel_type

            # Execute query
            relationships = list(
                self.db.relationships.find(query)
                .sort("weight", pymongo.DESCENDING)
                .limit(limit)
            )

            return relationships

        except Exception as e:
            logger.error(f"Error getting relationships from MongoDB: {str(e)}")
            return []

    def keyword_search(
        self,
        query: str,
        pdf_id: Optional[str] = None,
        content_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Perform keyword search on content elements.

        Args:
            query: Search query
            pdf_id: Optional PDF ID to filter by
            content_types: Optional content types to filter by
            limit: Maximum number of results to return

        Returns:
            List of matching content elements
        """
        if not self._initialized:
            if not self.initialize():
                return []

        try:
            # Extract terms from query
            terms = [term.strip() for term in query.split() if len(term.strip()) > 2]
            if not terms:
                return []

            # Build regex pattern for search
            regex_pattern = "|".join([f"(?i){term}" for term in terms])

            # Build query
            text_query = {"content": {"$regex": regex_pattern}}

            if pdf_id:
                text_query["pdf_id"] = pdf_id

            if content_types:
                text_query["content_type"] = {"$in": content_types}

            # Execute query
            results = list(
                self.db.content_elements.find(text_query)
                .limit(limit)
            )

            # Add synthetic score based on term frequency
            for result in results:
                content = result.get("content", "").lower()
                score = sum(content.count(term.lower()) for term in terms)
                result["score"] = min(1.0, score / 10)  # Normalize score to 0-1

            # Sort by score
            results.sort(key=lambda x: x.get("score", 0), reverse=True)

            return results

        except Exception as e:
            logger.error(f"Error performing keyword search in MongoDB: {str(e)}")
            return []

    def delete_document(self, pdf_id: str) -> bool:
        """
        Delete a document and all related content from MongoDB.

        Args:
            pdf_id: PDF ID

        Returns:
            Success status
        """
        if not self._initialized:
            if not self.initialize():
                return False

        try:
            # Delete document
            self.db.documents.delete_one({"pdf_id": pdf_id})

            # Delete content elements
            self.db.content_elements.delete_many({"pdf_id": pdf_id})

            # Delete concepts
            self.db.concepts.delete_many({"pdf_id": pdf_id})

            # Delete relationships
            self.db.relationships.delete_many({"pdf_id": pdf_id})

            logger.info(f"Deleted document {pdf_id} and related content from MongoDB")
            return True

        except Exception as e:
            logger.error(f"Error deleting document from MongoDB: {str(e)}")
            return False

    def close(self) -> None:
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            self.client = None
            self._initialized = False
            logger.info("MongoDB connection closed")

    async def check_health(self) -> Dict[str, Any]:
        """
        Check MongoDB health and connectivity.

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
            health_info["error"] = "MongoDB client not initialized"
            return health_info

        try:
            # Test basic connectivity
            self.client.admin.command('ping')

            # Check collection stats
            stats = {
                "documents": self.db.documents.count_documents({}),
                "content_elements": self.db.content_elements.count_documents({}),
                "concepts": self.db.concepts.count_documents({}),
                "relationships": self.db.relationships.count_documents({})
            }

            health_info.update({
                "connection": "connected",
                "status": "ok",
                "database_ready": True,
                "stats": stats
            })

            return health_info

        except Exception as e:
            health_info["error"] = str(e)
            return health_info

    def get_stats(self) -> Dict[str, Any]:
        """
        Get enhanced statistics about the MongoDB store.

        Returns:
            Dictionary with MongoDB statistics
        """
        if not self._initialized:
            if not self.initialize():
                return {"error": "MongoDB not initialized"}

        try:
            stats = {
                "collection_counts": {},
                "document_stats": {},
                "timestamp": datetime.utcnow().isoformat()
            }

            # Get collection counts
            for collection_name in ["documents", "content_elements", "concepts", "relationships", "procedures", "parameters"]:
                try:
                    if hasattr(self.db, collection_name):
                        collection = getattr(self.db, collection_name)
                        stats["collection_counts"][collection_name] = collection.count_documents({})
                except Exception as coll_err:
                    stats["collection_counts"][collection_name] = f"error: {str(coll_err)}"

            # Get document stats
            if hasattr(self.db, "documents"):
                # Count documents by metadata fields
                try:
                    # Count by category
                    category_pipeline = [
                        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
                        {"$sort": {"count": -1}}
                    ]
                    category_counts = list(self.db.documents.aggregate(category_pipeline))
                    stats["document_stats"]["categories"] = {item["_id"] or "unknown": item["count"] for item in category_counts}

                    # Count by processing status (if field exists)
                    status_pipeline = [
                        {"$group": {"_id": "$processed", "count": {"$sum": 1}}},
                        {"$sort": {"count": -1}}
                    ]
                    status_counts = list(self.db.documents.aggregate(status_pipeline))
                    stats["document_stats"]["processed_status"] = {str(item["_id"]): item["count"] for item in status_counts}

                except Exception as doc_err:
                    stats["document_stats"]["error"] = str(doc_err)

            # Get concept stats
            if hasattr(self.db, "concepts"):
                try:
                    # Count by primary vs regular concepts
                    primary_pipeline = [
                        {"$group": {"_id": "$is_primary", "count": {"$sum": 1}}},
                        {"$sort": {"count": -1}}
                    ]
                    primary_counts = list(self.db.concepts.aggregate(primary_pipeline))
                    stats["concept_stats"] = {
                        "primary_vs_regular": {str(item["_id"]): item["count"] for item in primary_counts},
                        "total": sum(item["count"] for item in primary_counts)
                    }

                    # Get document with most concepts
                    doc_concept_pipeline = [
                        {"$group": {"_id": "$pdf_id", "count": {"$sum": 1}}},
                        {"$sort": {"count": -1}},
                        {"$limit": 5}
                    ]
                    doc_concept_counts = list(self.db.concepts.aggregate(doc_concept_pipeline))
                    stats["concept_stats"]["top_documents"] = {item["_id"]: item["count"] for item in doc_concept_counts}

                except Exception as concept_err:
                    stats["concept_stats"]["error"] = str(concept_err)

            return stats

        except Exception as e:
            logger.error(f"Error getting MongoDB stats: {str(e)}")
            return {"error": str(e)}

# Singleton instance getter
def get_mongo_store() -> MongoStore:
    """Get or create MongoDB store instance"""
    return MongoStore()
