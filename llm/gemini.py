from google.generativeai import configure, GenerativeModel, GenerationConfig
from src.config.settings import GOOGLE_API_KEY, LLM_MODEL_NAME
import logging

logging.basicConfig(level=logging.INFO)

def get_gemini_response(prompt: str) -> str | None:
    """Calls the Gemini API with the given prompt."""
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "YOUR_GOOGLE_AI_STUDIO_API_KEY":
        logging.error("Google AI Studio API key not configured.")
        return None # Indicate failure

    try:
        configure(api_key=GOOGLE_API_KEY)
        logging.info(f"Using LLM model: {LLM_MODEL_NAME}")
        model = GenerativeModel(LLM_MODEL_NAME)

        # Configure generation parameters for more controlled output
        # Adjust these based on testing the 'tweak' prompt
        generation_config = GenerationConfig(
            temperature=0.1,  # Lower temperature for less creativity, more directness
            max_output_tokens=2048, # Ensure enough tokens for the full prompt
            # response_mime_type="text/plain" # Explicitly request plain text if available/needed
        )
        
        logging.info("Calling Gemini API...")
        response = model.generate_content(prompt, generation_config=generation_config)

        # Check for response text, handle potential safety blocks or empty responses
        if hasattr(response, 'text'):
            logging.info("✅ Received valid response from Gemini.")
            return response.text
        else:
            logging.warning("⚠️ LLM response did not contain text.")
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                 logging.warning(f"Block reason: {response.prompt_feedback.block_reason}")
                 # Depending on your needs, you might return an error message or None
                 return None # Indicate failure due to block

            logging.warning("LLM response structure unexpected.")
            return None # Indicate failure

    except Exception as e:
        logging.error(f"Error calling Gemini API: {e}")
        # Check for specific API errors if needed
        return None # Indicate failure