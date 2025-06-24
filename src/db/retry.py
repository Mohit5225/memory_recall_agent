import asyncio
import functools
import logging
from typing import TypeVar, Callable, Any, Awaitable
from pymongo.errors import PyMongoError
from typing import cast

logger = logging.getLogger(__name__)

T = TypeVar('T')

def with_retry(
    max_retries: int = 3,
    initial_delay: float = 0.1,
    max_delay: float = 2.0,
    exponential_base: float = 2.0,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any):
            last_error: PyMongoError | None = None
            delay = initial_delay

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except PyMongoError as e:
                    last_error = e
                    if attempt == max_retries - 1:
                        logger.error(
                            f"Failed after {max_retries} retries: {str(e)}",
                            exc_info=True
                        )
                        raise last_error

                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries} failed, "
                        f"retrying in {delay:.2f}s: {str(e)}"
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * exponential_base, max_delay)

            if last_error is not None:
                raise last_error

        return cast(Callable[..., Awaitable[T]], wrapper)
    return decorator