import logging
import asyncio
import google.generativeai as genai
from google.api_core import exceptions
from src.config.settings import GOOGLE_API_KEY, LLM_MODEL_NAME
from datetime import datetime
from typing import Optional, Tuple
import json

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
genai.configure(api_key=GOOGLE_API_KEY)

async def get_gemini_response_async(prompt: str, message_context: Optional[dict] = None, max_retries: int = 3) -> Tuple[Optional[str], dict]:
    """
    Get response from Gemini with proper error handling and status tracking.
    Returns both the response and updated context with processing status.
    
    Args:
        prompt: The text prompt to send to Gemini
        message_context: Optional dictionary containing context about the message
        max_retries: Maximum number of retry attempts for recoverable errors
        
    Returns:
        Tuple of (response_text, context_dict) where response_text may be None on error
        and context_dict contains processing status and error details
    """
    if not GOOGLE_API_KEY or "YOUR_KEY" in GOOGLE_API_KEY:
        logging.error("Invalid API key configuration")
        return None, {"processing_status": "failed", "error_details": "Invalid API configuration"}
    
    model = genai.GenerativeModel(LLM_MODEL_NAME)
    context = message_context or {}
    context["processing_attempts"] = context.get("processing_attempts", 0) + 1
    context["last_attempt"] = datetime.utcnow()
    context["processing_status"] = "processing"
    
    # Debug log the exact prompt and context being sent
    logger.debug("=== LLM Request Details ===")
    logger.debug(f"Prompt: {prompt}")
    if message_context:
        logger.debug(f"Context: {json.dumps(message_context, indent=2)}")
    
    # Create safety config
    safety_settings = {
        "HARASSMENT": "BLOCK_MEDIUM_AND_ABOVE",
        "HATE_SPEECH": "BLOCK_MEDIUM_AND_ABOVE",
        "SEXUALLY_EXPLICIT": "BLOCK_MEDIUM_AND_ABOVE",
        "DANGEROUS_CONTENT": "BLOCK_MEDIUM_AND_ABOVE"
    }

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                delay = min(2 ** attempt, 32)  # Cap at 32 seconds
                logging.info(f"Retrying after {delay}s delay (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(delay)
            
            logging.info(f"Sending prompt to Gemini (attempt {attempt + 1}/{max_retries}): {prompt[:100]}...")
            response = await model.generate_content_async(
                contents=[{"parts": [{"text": prompt}]}],
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 2048
                }
            )
            
            if not hasattr(response, 'text'):
                error_msg = "Response missing text attribute"
                logging.warning(f"{error_msg} on attempt {attempt + 1}")
                if attempt == max_retries - 1:
                    context["processing_status"] = "failed"
                    context["error_details"] = error_msg
                    context["error_type"] = "invalid_response"
                    return None, context
                continue
            
            # Success case
            context["processing_status"] = "completed"
            context["error_details"] = None
            context["error_type"] = None
            return response.text, context

        except exceptions.InvalidArgument as e:
            error_msg = f"Invalid argument: {str(e)}"
            logging.error(error_msg)
            context["processing_status"] = "failed"
            context["error_details"] = error_msg
            context["error_type"] = "invalid_argument"
            return None, context  # Don't retry on invalid arguments

        except exceptions.ResourceExhausted as e:
            error_msg = f"Resource quota exceeded: {str(e)}"
            logging.warning(f"{error_msg} on attempt {attempt + 1}")
            if attempt == max_retries - 1:
                context["processing_status"] = "failed"
                context["error_details"] = error_msg
                context["error_type"] = "resource_exhausted"
                return None, context
            continue  # Will retry with backoff

        except exceptions.DeadlineExceeded as e:
            error_msg = f"Request deadline exceeded: {str(e)}"
            logging.warning(f"{error_msg} on attempt {attempt + 1}")
            if attempt == max_retries - 1:
                context["processing_status"] = "failed"
                context["error_details"] = error_msg
                context["error_type"] = "deadline_exceeded"
                return None, context
            continue  # Will retry with backoff

        except exceptions.ServiceUnavailable as e:
            error_msg = f"Service unavailable: {str(e)}"
            logging.warning(f"{error_msg} on attempt {attempt + 1}")
            if attempt == max_retries - 1:
                context["processing_status"] = "failed"
                context["error_details"] = error_msg
                context["error_type"] = "service_unavailable"
                return None, context
            continue  # Will retry with backoff

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logging.error(f"{error_msg} on attempt {attempt + 1}")
            context["processing_status"] = "failed"
            context["error_details"] = error_msg
            context["error_type"] = "unexpected"
            return None, context  # Don't retry on unknown errors

    # Should never reach here due to returns in the loop
    context["processing_status"] = "failed"
    context["error_details"] = "Maximum retries exceeded"
    context["error_type"] = "max_retries"
    return None, context