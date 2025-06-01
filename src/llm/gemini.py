import logging
import asyncio
from google.api_core import exceptions
from google.generativeai import Client, GenerationConfig
from src.config.settings import GOOGLE_API_KEY, LLM_MODEL_NAME

logging.basicConfig(level=logging.INFO)
genai_client = Client()

async def get_gemini_response_async(prompt: str, retries: int = 3) -> str | None:
    if not GOOGLE_API_KEY or "YOUR_KEY" in GOOGLE_API_KEY:
        logging.error("Invalid API key configuration")
        return None
    for attempt in range(retries):
        try:
            response = await genai_client.aio.models.generate_content(
                model=LLM_MODEL_NAME,
                contents=[{"parts": [{"text": prompt}]}],
                generation_config=GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=2048
                )
            )
            if response.candidates and response.candidates[0].content.parts:
                logging.info("✅ Received valid async response from Gemini.")
                return response.candidates[0].content.parts[0].text
            logging.warning(f"Unexpected response structure: {response}")
            if response.prompt_feedback and response.prompt_feedback.block_reason:
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