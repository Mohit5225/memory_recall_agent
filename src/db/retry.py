import asyncio
import functools
import logging
from typing import TypeVar, Callable, Any
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

T = TypeVar('T')

def with_retry(
    max_retries: int = 3,
    initial_delay: float = 0.1,
    max_delay: float = 2.0,
    exponential_base: float = 2.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    A decorator that implements exponential backoff retry logic for database operations.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff calculation
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except PyMongoError as e:
                    last_error = e
                    if attempt == max_retries:
                        logger.error(
                            f"Operation failed after {max_retries} retries: {str(e)}",
                            exc_info=True
                        )
                        raise
                    
                    logger.warning(
                        f"Operation failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay:.2f}s: {str(e)}"
                    )
                    
                    await asyncio.sleep(delay)
                    delay = min(delay * exponential_base, max_delay)

            raise last_error  # Should never reach here, but keeps type checker happy
            
        return wrapper
    return decorator
