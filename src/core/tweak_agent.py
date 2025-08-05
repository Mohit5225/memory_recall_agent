import logging
from src.db.mongo import get_user_config, save_user_config, normalize_user_config
from src.llm.gemini import get_gemini_response_async

logging.basicConfig(level=logging.INFO)

# --- Prompt Engineering for the Tweak Agent ---
# This is the core instruction for the LLM to perform the editing task.
# Ensure this prompt is clear, specifies the input format (tags),
# the task (edit existing based on new), and the output format (only revised text).
TWEAK_AGENT_PROMPT_TEMPLATE = """
Act as a configuration editor agent for a knowledge reminder system.
Your task is to update a user's detailed reminder generation instructions based on their new request.

Below are the user's CURRENT, complete instructions for generating reminder content, enclosed in <EXISTING_INSTRUCTIONS> tags.
<EXISTING_INSTRUCTIONS>
{existing_instructions}
</EXISTING_INSTRUCTIONS>

Below is the user's NEW request for modification, enclosed in <NEW_REQUEST> tags.
<NEW_REQUEST>
{new_instruction}
</NEW_REQUEST>

Analyze the <NEW_REQUEST> carefully. Identify the user's intended changes to the instructions. Apply *only* the requested modifications to the text within <EXISTING_INSTRUCTIONS>. Preserve *all other text* in the <EXISTING_INSTRUCTIONS> exactly as it was. Maintain the overall structure and format of the original instructions.

Output ONLY the complete, revised text of the instructions. Do NOT include any introductory phrases, commentary, explanations, or anything outside of the final, updated instruction text itself. Ensure the output is ready to be used as a system prompt for another AI.
"""

# --- Default Instructions ---
# This is the starting instruction set used if a user has no existing config in the DB.
# REPLACE THIS WITH YOUR ACTUAL, DETAILED MULTI-LINE DEFAULT PROMPT
DEFAULT_INSTRUCTIONS = """
# Default Reminder Agent Configuration

# --- Core Function ---
# This agent generates brief, bite-sized knowledge reminders.
# It is NOT meant for deep teaching or conversational dialogue beyond setting preferences.

# --- Reminder Topic ---
# Current Topic: pytorch methods and functions

# --- Reminder Style/Manner ---
# Style: Quick, factual.
# Tone: witty , uplifting, and engaging.
# Length: Max 15-20 sentences.


# --- Constraints ---
# 1. Always stay on the specified topic.
# 2. Do not explain concepts in depth. Just provide a brief reminder of their existence or a key characteristic.
# 3. Never engage in chat outside of configuration updates.
# 4. If asked a question about the topic, the answer should be a reminder, not a lesson.
# 5. do not engage in conversation outside of configuration updates If the user asks for explanation do it briefly and if ask for
  deep explanation,and politely offer if they want reminders on whatsapp and decline if they ask it on web platform and suggest they refer to documentation or tutorials and if they allow on whatsapp 
   Use code blocks for code.  
- Use bullet points for explanations.  
- Use headings for sections.  
- Do not mix code and explanation in the same block.
# 6. w examples.
# --- Example (for the AI to understand the format) ---
# Example Reminder: "Reminder: 'ls' command lists directory contents in Linux."
""" # End of default instructions. Replace this block.


# --- Core Function ---
async def process_user_instruction(user_id: str, new_instruction: str) -> bool:
    """
    Processes a new instruction from a user to update their configuration.
    Uses modular DB and LLM components.

    Args:
        user_id: The ID of the user.
        new_instruction: The natural language instruction from the user.

    Returns:
        True if the configuration was successfully updated or deemed not needing change, False otherwise.
    """
    logging.info(f"Processing instruction for user: {user_id} - '{new_instruction}'")

    try:
        # 1. Get and normalize existing config from DB
        raw_existing = await get_user_config(user_id)
        if raw_existing is None:
            logging.error(f"Failed to retrieve user config for {user_id}. Cannot proceed.")
            return False
        norm_existing = normalize_user_config(raw_existing)
        current_instructions = norm_existing['full_instruction_prompt'] or DEFAULT_INSTRUCTIONS.strip()

        # 2. Construct the prompt for the LLM to perform the 'tweak'
        llm_prompt = TWEAK_AGENT_PROMPT_TEMPLATE.format(
            existing_instructions=current_instructions,
            new_instruction=new_instruction
        ).strip()  # Strip prompt whitespace

        logging.info("Constructed LLM prompt for tweaking.")
        # 3. Call the LLM API to get the revised instructions
        logging.info("Calling LLM to revise instructions...")
        revised_instructions, context = await get_gemini_response_async(llm_prompt)
        logging.info(f"LLM context info: {context}")

        if revised_instructions is None:
            # Enhanced error handling using context information
            error_type = context.get("error_type", "unknown")
            error_details = context.get("error_details", "No details available")
            processing_attempts = context.get("processing_attempts", 0)
            
            # Context-aware error messages
            if error_type == "api_key_invalid":
                logging.error(f"LLM API key configuration error for user {user_id}. Cannot proceed with config update.")
            elif error_type == "quota_exceeded":
                logging.error(f"LLM API quota exceeded for user {user_id}. Consider retry later or use fallback.")
            elif error_type == "rate_limit":
                logging.error(f"LLM API rate limit hit for user {user_id} after {processing_attempts} attempts.")
            elif error_type == "max_retries":
                logging.error(f"LLM failed after {processing_attempts} retry attempts for user {user_id}. Error: {error_details}")
            else:
                logging.error(f"Failed to get valid LLM response for user {user_id}. Error type: {error_type}, Details: {error_details}")
            
            # Enhanced context logging for debugging
            logging.info(f"LLM failure context - Type: {error_type}, Attempts: {processing_attempts}, Status: {context.get('processing_status', 'unknown')}")
            
            return False  # Indicate failure

        # Ensure the LLM returned text and strip potential surrounding quotes/whitespace
        revised_instructions = revised_instructions.strip().strip('`').strip()  # Basic cleaning
        # 4. Merge into full config and save
        full_conf = normalize_user_config(raw_existing)
        full_conf['full_instruction_prompt'] = revised_instructions
        logging.info("Saving revised instructions to DB...")
        save_success = await save_user_config(user_id, full_conf)

        if save_success:
            logging.info(f"✅ User {user_id} config update process completed.")
            # Enhanced success logging with context information
            if context:
                processing_status = context.get("processing_status", "unknown")
                processing_attempts = context.get("processing_attempts", 0)
                logging.info(f"LLM processing successful - Status: {processing_status}, Attempts: {processing_attempts}")
            # Preview first lines
            logging.info("Preview of updated config (first 5 non-empty lines):")
            lines = revised_instructions.split('\n')
            non_empty = [l for l in lines if l.strip()]
            logging.info('\n'.join(non_empty[:5]))
            return True  # Indicate success
        else:
            # Enhanced database save error handling
            logging.error(f"Failed to save revised config for user {user_id}.")
            if context:
                proc_stat = context.get("processing_status", "unknown")
                logging.warning(f"LLM processing context at DB save failure - Status: {proc_stat}, Attempts: {context.get('processing_attempts', 0)}")
            return False  # Indicate failure

    except Exception as e:
        # Enhanced general exception handling with context information
        logging.error(f"Error processing instruction for user {user_id}: {e}", exc_info=True)
        
        # Log context information if available for debugging
        try:
            if 'context' in locals() and context:
                error_context = {
                    "processing_status": context.get("processing_status", "unknown"),
                    "processing_attempts": context.get("processing_attempts", 0),
                    "error_type": context.get("error_type", "unknown"),
                    "last_attempt": context.get("last_attempt", "unknown")
                }
                logging.info(f"Exception occurred with LLM context: {error_context}")
        except Exception as ctx_error:
            # Prevent context logging from causing additional failures
            logging.debug(f"Could not log context information: {ctx_error}")
        
        return False  # Indicate failure