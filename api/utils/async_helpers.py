"""
Async utilities for standardized async operations.
This module provides helpers for managing async operations safely.
"""

import asyncio
import logging
import time
import functools
from typing import Any, Callable, Coroutine, Optional, TypeVar, Dict, List, Union

logger = logging.getLogger(__name__)

T = TypeVar('T')  # Return type for coroutines

async def with_timeout(
    coro: Coroutine[Any, Any, T],
    timeout: float = 10.0,
    fallback: Optional[T] = None,
    operation_name: str = "Operation"
) -> T:
    """
    Execute a coroutine with timeout protection.

    Args:
        coro: Coroutine to execute
        timeout: Timeout in seconds
        fallback: Value to return on timeout
        operation_name: Name of the operation for logging

    Returns:
        Result of coroutine or fallback on timeout
    """
    try:
        start_time = time.time()
        result = await asyncio.wait_for(coro, timeout=timeout)
        execution_time = time.time() - start_time
        logger.debug(f"{operation_name} completed in {execution_time:.2f}s")
        return result
    except asyncio.TimeoutError:
        logger.warning(f"{operation_name} timed out after {timeout:.2f}s")
        return fallback
    except Exception as e:
        logger.error(f"{operation_name} failed: {str(e)}")
        return fallback

def run_async(coro: Coroutine[Any, Any, T], timeout: float = 30.0) -> T:
    """
    Run an async function in a synchronous context with proper cleanup.
    Safely handles cases where it's called from within an existing event loop.

    Args:
        coro: Coroutine to execute
        timeout: Timeout in seconds

    Returns:
        Result of the coroutine execution
    """
    # Check if we're already in an event loop
    try:
        current_loop = asyncio.get_running_loop()
        # If we get here, we're already in an event loop
        # Use run_coroutine_threadsafe to run in the existing loop from a different thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = asyncio.run_coroutine_threadsafe(coro, current_loop)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                future.cancel()
                logger.warning(f"Async operation timed out after {timeout}s")
                return None
            except Exception as e:
                logger.error(f"Error in threaded async execution: {str(e)}")
                return None
    except RuntimeError:
        # No event loop running, create a new one
        loop = asyncio.new_event_loop()

        try:
            # Set the loop as current
            asyncio.set_event_loop(loop)

            # Create a task and run it with timeout
            task = loop.create_task(coro)
            return loop.run_until_complete(asyncio.wait_for(task, timeout=timeout))
        finally:
            # Clean up: cancel all pending tasks
            pending_tasks = [task for task in asyncio.all_tasks(loop)
                            if not task.done() and task != asyncio.current_task(loop)]

            if pending_tasks:
                for task in pending_tasks:
                    task.cancel()

                # Wait for tasks to cancel
                if loop.is_running():
                    loop.create_task(asyncio.gather(*pending_tasks, return_exceptions=True))
                else:
                    loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))

            # Close the loop
            loop.close()

def to_async(func: Callable) -> Callable:
    """
    Convert a synchronous function to an asynchronous one.

    Args:
        func: Synchronous function to convert

    Returns:
        Async version of the function
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

def to_sync(coro_func: Callable) -> Callable:
    """
    Convert an asynchronous function to a synchronous one.

    Args:
        coro_func: Async function to convert

    Returns:
        Sync version of the function
    """
    @functools.wraps(coro_func)
    def wrapper(*args, **kwargs):
        coro = coro_func(*args, **kwargs)
        return run_async(coro)
    return wrapper

class AsyncExecutor:
    """
    Helper class for executing multiple async operations.
    Manages timeouts and retries for multiple operations.
    """

    def __init__(self, timeout: float = 30.0, retry_count: int = 3):
        """
        Initialize the async executor.

        Args:
            timeout: Default timeout in seconds
            retry_count: Default number of retries
        """
        self.timeout = timeout
        self.retry_count = retry_count
        self.tasks = {}
        self.results = {}
        self.errors = {}

    async def execute(
        self,
        name: str,
        coro: Coroutine[Any, Any, T],
        timeout: Optional[float] = None,
        retry_count: Optional[int] = None,
        fallback: Any = None
    ) -> T:
        """
        Execute a coroutine with timeout and retry protection.

        Args:
            name: Operation name
            coro: Coroutine to execute
            timeout: Timeout in seconds (overrides default)
            retry_count: Number of retries (overrides default)
            fallback: Value to return on failure

        Returns:
            Result of the coroutine execution
        """
        # Use class defaults if not specified
        actual_timeout = timeout if timeout is not None else self.timeout
        actual_retry_count = retry_count if retry_count is not None else self.retry_count

        for attempt in range(actual_retry_count + 1):
            try:
                # Create a task for this coroutine
                task = asyncio.create_task(coro)
                self.tasks[name] = task

                # Execute with timeout
                result = await asyncio.wait_for(task, timeout=actual_timeout)

                # Store result
                self.results[name] = result
                return result

            except asyncio.TimeoutError:
                logger.warning(f"{name} timed out after {actual_timeout}s (attempt {attempt+1}/{actual_retry_count+1})")
                if attempt < actual_retry_count:
                    # Exponential backoff for retries
                    retry_delay = 0.1 * (2 ** attempt)
                    await asyncio.sleep(retry_delay)
                else:
                    error = f"Operation timed out after {actual_retry_count+1} attempts"
                    self.errors[name] = error
                    return fallback

            except Exception as e:
                logger.error(f"{name} failed: {str(e)} (attempt {attempt+1}/{actual_retry_count+1})")
                if attempt < actual_retry_count:
                    # Exponential backoff for retries
                    retry_delay = 0.1 * (2 ** attempt)
                    await asyncio.sleep(retry_delay)
                else:
                    error = str(e)
                    self.errors[name] = error
                    return fallback

    async def execute_all(
        self,
        operations: Dict[str, Coroutine[Any, Any, Any]],
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Execute multiple coroutines concurrently.

        Args:
            operations: Dict mapping operation names to coroutines
            timeout: Overall timeout for all operations

        Returns:
            Dict mapping operation names to results
        """
        # Reset results and errors
        self.results = {}
        self.errors = {}

        # Use class default timeout if not specified
        actual_timeout = timeout if timeout is not None else self.timeout

        # Create tasks for all operations
        for name, coro in operations.items():
            self.tasks[name] = asyncio.create_task(coro)

        # Wait for all tasks to complete with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*self.tasks.values(), return_exceptions=True),
                timeout=actual_timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Overall operation timed out after {actual_timeout}s")

            # Cancel any pending tasks
            for name, task in self.tasks.items():
                if not task.done():
                    task.cancel()
                    self.errors[name] = "Operation timed out"

        # Collect results
        for name, task in self.tasks.items():
            if name not in self.errors:
                if task.done():
                    try:
                        result = task.result()
                        self.results[name] = result
                    except Exception as e:
                        self.errors[name] = str(e)
                else:
                    self.errors[name] = "Operation did not complete"

        # Return results with None for failed operations
        results = {}
        for name in operations.keys():
            results[name] = self.results.get(name)

        return results

async def gather_with_concurrency(n: int, *tasks) -> List[Any]:
    """
    Run coroutines with a concurrency limit.

    Args:
        n: Maximum number of coroutines to run concurrently
        tasks: Coroutines to execute

    Returns:
        List of results in the same order as tasks
    """
    semaphore = asyncio.Semaphore(n)

    async def sem_task(task):
        async with semaphore:
            return await task

    return await asyncio.gather(*(sem_task(task) for task in tasks))
