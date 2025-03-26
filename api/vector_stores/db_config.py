"""
Configuration module for database connections.
Centralizes configuration management for MongoDB and Qdrant.
"""

import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class DatabaseConfig:
    """
    Database configuration manager.
    Provides centralized access to database connection settings.
    """

    # MongoDB Settings
    MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/")
    MONGODB_DB_NAME = os.environ.get("MONGODB_DB_NAME", "tech_rag")

    # Qdrant Settings
    QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
    QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))
    QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "content_vectors")

    # Embedding Settings
    EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIMENSION = int(os.environ.get("EMBEDDING_DIMENSION", "1536"))

    @classmethod
    def get_mongodb_config(cls) -> Dict[str, Any]:
        """
        Get MongoDB configuration.

        Returns:
            MongoDB configuration dictionary
        """
        return {
            "uri": cls.MONGODB_URI,
            "db_name": cls.MONGODB_DB_NAME
        }

    @classmethod
    def get_qdrant_config(cls) -> Dict[str, Any]:
        """
        Get Qdrant configuration.

        Returns:
            Qdrant configuration dictionary
        """
        return {
            "url": cls.QDRANT_HOST,
            "port": cls.QDRANT_PORT,
            "collection_name": cls.QDRANT_COLLECTION,
            "embedding_dimension": cls.EMBEDDING_DIMENSION,
            "embedding_model": cls.EMBEDDING_MODEL
        }

    @classmethod
    def get_neo4j_config(cls) -> Dict[str, Any]:
        """
        Get Neo4j configuration (for migration).

        Returns:
            Neo4j configuration dictionary
        """
        return {
            "url": cls.NEO4J_URL,
            "username": cls.NEO4J_USER,
            "password": cls.NEO4J_PASSWORD
        }

    @classmethod
    def initialize_from_env(cls) -> None:
        """Initialize configuration from environment variables."""
        # MongoDB Settings
        cls.MONGODB_URI = os.environ.get("MONGODB_URI", cls.MONGODB_URI)
        cls.MONGODB_DB_NAME = os.environ.get("MONGODB_DB_NAME", cls.MONGODB_DB_NAME)

        # Qdrant Settings
        cls.QDRANT_HOST = os.environ.get("QDRANT_HOST", cls.QDRANT_HOST)
        cls.QDRANT_PORT = int(os.environ.get("QDRANT_PORT", cls.QDRANT_PORT))
        cls.QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", cls.QDRANT_COLLECTION)

        # Embedding Settings
        cls.EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", cls.EMBEDDING_MODEL)
        cls.EMBEDDING_DIMENSION = int(os.environ.get("EMBEDDING_DIMENSION", cls.EMBEDDING_DIMENSION))

        logger.info("Database configuration initialized from environment")

    @classmethod
    def validate_config(cls) -> Dict[str, bool]:
        """
        Validate configuration settings.

        Returns:
            Dictionary with validation results
        """
        results = {
            "mongodb_uri_valid": bool(cls.MONGODB_URI),
            "mongodb_db_name_valid": bool(cls.MONGODB_DB_NAME),
            "qdrant_host_valid": bool(cls.QDRANT_HOST),
            "qdrant_port_valid": cls.QDRANT_PORT > 0,
            "embedding_model_valid": bool(cls.EMBEDDING_MODEL),
            "embedding_dimension_valid": cls.EMBEDDING_DIMENSION > 0
        }

        # Overall success
        results["all_valid"] = all(results.values())

        return results

# Initialize on module import
DatabaseConfig.initialize_from_env()
