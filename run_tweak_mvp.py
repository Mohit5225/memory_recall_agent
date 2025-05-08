import sys
import logging
from src.core.tweak_agent import process_user_instruction

# Configure basic logging for the script's output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if __name__ == "__main__":
    logging.info("🚀 Starting Memory Recall Agent Config Tweak MVP")

    # Expecting user_id and the new instruction text as command-line arguments
    if len(sys.argv) < 3:
        logging.error("Usage: python run_tweak_mvp.py <user_id> '<new instruction text>'")
        logging.error("Example: python run_tweak_mvp.py user123 'Change topic to FastAPI and make reminders concise.'")
        sys.exit(1)

    user_id = sys.argv[1]
    # Join all subsequent arguments to allow multi-word instructions
    new_instruction = " ".join(sys.argv[2:])

    logging.info(f"Received instruction for user: {user_id}")
    logging.info(f"Instruction: '{new_instruction}'")

    # Call the main processing function from the core module
    success = process_user_instruction(user_id, new_instruction)

    if success:
        logging.info("🎉 Operation completed successfully!")
    else:
        logging.error("❌ Operation failed.")