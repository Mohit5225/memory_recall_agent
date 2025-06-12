import logging
import asyncio
import google.generativeai as genai
from google.api_core import exceptions
from src.config.settings import GOOGLE_API_KEY, LLM_MODEL_NAME
from datetime import datetime
from typing import Optional, Tuple

logging.basicConfig(level=logging.INFO)
genai.configure(api_key=GOOGLE_API_KEY)

async def get_gemini_response_async(prompt: str, message_context: Optional[dict] = None, max_retries: int = 3) -> Tuple[Optional[str], dict]:
    """
    Get response from Gemini with proper error handling and status tracking.
    Returns both the response and updated context with processing status.
    """
    if not GOOGLE_API_KEY or "YOUR_KEY" in GOOGLE_API_KEY:
        logging.error("Invalid API key configuration")
        return None, {"processing_status": "failed", "error_details": "Invalid API configuration"}
    
    model = genai.GenerativeModel(LLM_MODEL_NAME)
    context = message_context or {}
    context["processing_attempts"] = context.get("processing_attempts", 0) + 1
    context["last_attempt"] = datetime.utcnow()
    context["processing_status"] = "processing"
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:  # Add exponential backoff delay for retries
                delay = min(2 ** attempt, 32)  # Cap at 32 seconds
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
                if attempt == max_retries - 1:  # Only fail on last attempt
                    context["processing_status"] = "failed"
                    context["error_details"] = "Response missing text attribute"
                    return None, context
                continue  # Try again if we have attempts left
            
            # Success case
            context["processing_status"] = "completed"
            context["error_details"] = None
            return response.text, context

        except exceptions.ResourceExhausted:
            if attempt == max_retries - 1:
                context["processing_status"] = "failed"
                context["error_details"] = "Resource exhausted"
                return None, context
            # Will retry automatically due to the loop

        except Exception as e:
            logging.error(f"Unexpected error on attempt {attempt + 1}: {str(e)}")
            context["processing_status"] = "failed"
            context["error_details"] = f"Unexpected error: {str(e)}"
            return None, context  # Don't retry on unknown errors

    # Should never reach here due to returns in the loop
    context["processing_status"] = "failed"
    context["error_details"] = "Maximum retries exceeded"
    return None, context