import httpx
import logging
import json
from typing import Optional, Tuple, Dict, Any
from src.config.settings import OPENROUTER_SECRET_KEY

# Set up logging
logger = logging.getLogger(__name__)

# --- Constants ---
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

async def get_openrouter_response_async(prompt: str, model_name: str , message_context : Optional[dict]) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Asynchronously gets a response from a specified OpenRouter model.
    This function is now fortified to match the return signature of gemini.py,
    always returning a (text, context) tuple for consistent error handling.

    Args:
        prompt: The user's instruction or question.
        model_name: The specific model identifier from OpenRouter.

    Returns:
        A tuple containing (response_text, context_dict). response_text is None on failure.
    """
    if not OPENROUTER_SECRET_KEY:
        msg = "OPENROUTER_SECRET_KEY is not set. Cannot make fallback call."
        logger.error(msg)
        return None, {"llm_provider": "openrouter", "error_details": msg, "processing_status": "failed"}

    headers = {
        "Authorization": f"Bearer {OPENROUTER_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}]
    }
    context = message_context or {}
    logger.info(f"Attempting fallback call to OpenRouter model: {model_name}")
    if message_context:
        logger.debug(f"Fallback initiated with context: {json.dumps(context, indent=2)}")



    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            logger.info(f"Attempting fallback call to OpenRouter model: {model_name}")
            response = await client.post(OPENROUTER_API_URL, headers=headers, json=payload)
            response.raise_for_status()

            response_data = response.json()
            content = response_data.get("choices", [{}])[0].get("message", {}).get("content")

            if not content:
                msg = f"OpenRouter response for {model_name} was successful but content was empty."
                logger.error(msg)
                return None, {"llm_provider": "openrouter", "model_name": model_name, "error_details": msg, "processing_status": "failed"}

            context = {
                "llm_provider": "openrouter",
                "model_name": model_name,
                "usage": response_data.get("usage", {}),
                "finish_reason": response_data.get("choices", [{}])[0].get("finish_reason"),
                "processing_status": "completed"
            }
            logger.info(f"Successfully received response from OpenRouter model: {model_name}")
            return content.strip(), context

    except httpx.HTTPStatusError as e:
        error_text = e.response.text
        msg = f"HTTP error calling OpenRouter model {model_name}: {e.response.status_code} - {error_text}"
        logger.error(msg)
        return None, {"llm_provider": "openrouter", "model_name": model_name, "error_details": msg, "processing_status": "failed"}
    except Exception as e:
        msg = f"An unexpected error occurred calling OpenRouter model {model_name}: {e}"
        logger.error(msg)
        return None, {"llm_provider": "openrouter", "model_name": model_name, "error_details": msg, "processing_status": "failed"}