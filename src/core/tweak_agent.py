import logging
from src.db.mongo import get_user_config, save_user_config
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

# --- Example (for the AI to understand the format) ---
# Example Reminder: "Reminder: 'ls' command lists directory contents in Linux."
""" # End of default instructions. Replace this block.


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

    # 1. Get existing config from DB (or use default if none)
    existing_instructions = get_user_config(user_id)

    if existing_instructions is None:
        logging.error(f"Failed to retrieve user config for {user_id}. Cannot proceed.")
        return False # Indicate failure

    if not existing_instructions.strip(): # Check if fetched config is empty or just whitespace
        logging.info(f"No existing config found for {user_id} in DB. Using default instructions.")
        current_instructions = DEFAULT_INSTRUCTIONS.strip() # Use and strip default
    else:
         logging.info(f"Using existing config for {user_id} from DB.")
         current_instructions = existing_instructions.strip() # Use and strip fetched

    # 2. Construct the prompt for the LLM to perform the 'tweak'
    llm_prompt = TWEAK_AGENT_PROMPT_TEMPLATE.format(
        existing_instructions=current_instructions,
        new_instruction=new_instruction
    ).strip() # Strip prompt whitespace

    logging.info("Constructed LLM prompt for tweaking.")
    # Optional: uncomment to print the full prompt sent to LLM (can be large)
    # logging.info(f"--- Full Prompt sent to LLM ---\n{llm_prompt}\n--- End of Full Prompt ---")


    # 3. Call the LLM API to get the revised instructions
    logging.info("Calling LLM to revise instructions...")
    revised_instructions = await get_gemini_response_async(llm_prompt)

    if revised_instructions is None:
        logging.error("Failed to get a valid response from LLM to revise instructions.")
        return False # Indicate failure

    # Ensure the LLM returned text and strip potential surrounding quotes/whitespace
    revised_instructions = revised_instructions.strip().strip('`').strip() # Basic cleaning - refine later


    # 4. Save the revised instructions back to the DB
    logging.info("Saving revised instructions to DB...")
    save_success = save_user_config(user_id, revised_instructions)

    if save_success:
        logging.info(f"✅ User {user_id} config update process completed.")
        logging.info("Preview of updated config (first 5 non-empty lines):")
        lines = revised_instructions.split('\n')
        non_empty_lines = [line for line in lines if line.strip()]
        logging.info('\n'.join(non_empty_lines[:5]))
        return True # Indicate success
    else:
        logging.error(f"Failed to save revised config for user {user_id}.")
        return False # Indicate failure