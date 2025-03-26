"""
File and message serialization utilities.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Union, Optional

from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
    FunctionMessage
)

__all__ = [
    "save_json",
    "load_json",
    "create_message_from_dict",
    "serialize_message"
]

logger = logging.getLogger(__name__)


async def save_json(data: Any, file_path: Union[str, Path]) -> None:
    """
    Save data to JSON file asynchronously.

    Args:
        data: Data to save
        file_path: Path to save file
    """
    import aiofiles
    from .document import create_directory_if_not_exists

    if isinstance(file_path, str):
        file_path = Path(file_path)

    # Create parent directory if necessary
    create_directory_if_not_exists(file_path.parent)

    try:
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            # Handle datetime and other non-serializable types
            await f.write(json.dumps(data, default=str, indent=2))
    except Exception as e:
        logger.error(f"Failed to save JSON file {file_path}: {e}")
        raise


async def load_json(file_path: Union[str, Path]) -> Any:
    """
    Load data from JSON file asynchronously.

    Args:
        file_path: Path to load file from

    Returns:
        Loaded data
    """
    import aiofiles

    if isinstance(file_path, str):
        file_path = Path(file_path)

    try:
        if not file_path.exists():
            logger.warning(f"File {file_path} does not exist")
            return None

        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            return json.loads(content)
    except Exception as e:
        logger.error(f"Failed to load JSON file {file_path}: {e}")
        return None


def create_message_from_dict(data: Dict[str, Any]) -> BaseMessage:
    """
    Create a LangChain message from a dictionary with enhanced error handling.

    Args:
        data: Dictionary with message data

    Returns:
        LangChain message
    """
    try:
        role = data.get("role", "").lower()
        content = data.get("content", "")
        additional_kwargs = data.get("additional_kwargs", {})

        message_types = {
            "human": HumanMessage,
            "user": HumanMessage,
            "ai": AIMessage,
            "assistant": AIMessage,
            "system": SystemMessage,
            "tool": ToolMessage,
            "function": FunctionMessage,
        }

        message_class = message_types.get(role)
        if not message_class:
            logger.warning(f"Unknown message role: {role}, defaulting to HumanMessage")
            message_class = HumanMessage

        if message_class in (ToolMessage, FunctionMessage):
            return message_class(
                content=content,
                tool_call_id=additional_kwargs.get("tool_call_id"),
                name=additional_kwargs.get("name"),
                additional_kwargs=additional_kwargs,
            )
        else:
            return message_class(content=content, additional_kwargs=additional_kwargs)
    except Exception as e:
        logger.error(f"Error creating message: {str(e)}")
        return HumanMessage(content=str(data))


def serialize_message(message: BaseMessage) -> Dict[str, Any]:
    """
    Serialize a LangChain message to a dictionary with safe error handling.

    Args:
        message: LangChain message

    Returns:
        Dictionary representation of message
    """
    try:
        base_data = {
            "content": message.content,
            "type": message.type,
            "additional_kwargs": message.additional_kwargs,
        }

        if isinstance(message, HumanMessage):
            base_data["role"] = "human"
        elif isinstance(message, AIMessage):
            base_data["role"] = "ai"
        elif isinstance(message, SystemMessage):
            base_data["role"] = "system"
        elif isinstance(message, ToolMessage):
            base_data["role"] = "tool"
        elif isinstance(message, FunctionMessage):
            base_data["role"] = "function"
        else:
            base_data["role"] = "unknown"

        return base_data
    except Exception as e:
        logger.error(f"Error serializing message: {str(e)}")
        return {"role": "system", "content": "Error processing message", "additional_kwargs": {}}
