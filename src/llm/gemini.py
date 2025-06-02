import logging
import asyncio
import google.generativeai as genai
from google.api_core import exceptions
from src.config.settings import GOOGLE_API_KEY, LLM_MODEL_NAME

logging.basicConfig(level=logging.INFO)
genai.configure(api_key=GOOGLE_API_KEY)

async def get_gemini_response_async(prompt: str, retries: int = 3) -> str | None:
    if not GOOGLE_API_KEY or "YOUR_KEY" in GOOGLE_API_KEY:
        logging.error("Invalid API key configuration")
        return None
    
    model = genai.GenerativeModel(LLM_MODEL_NAME)
    
    for attempt in range(retries):
        try:
            response = await model.generate_content_async(
                contents=[{"parts": [{"text": prompt}]}],
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 2048
                }
            )
            if hasattr(response, 'text'):
                logging.info("✅ Received valid async response from Gemini.")
                return response.text
            logging.warning(f"Unexpected response structure: {response}")
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                logging.warning(f"Block reason: {response.prompt_feedback.block_reason}")
            return None
        except exceptions.ResourceExhausted:
            if attempt < retries - 1:
                delay = 2 ** attempt * 10
                logging.warning(f"Rate limit hit, retrying in {delay}s (attempt {attempt + 1}/{retries})")
                await asyncio.sleep(delay)
            else:
                logging.error("Max retries reached for rate limit")
                return None
        except Exception as e:
            logging.error(f"API Error: {str(e)}")
            return None