#!/usr/bin/env python3
"""
Debug script to test the unified LLM parsing directly.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).resolve().parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.schedular import parse_schedule_parameters_and_clarify
from src.llm.gemini import get_gemini_response_async
import logging

# Configure detailed logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_direct_llm_call():
    """Test direct LLM call to see what's happening"""
    print("🔍 TESTING: Direct LLM Call")
    print("=" * 50)
    
    test_prompt = """
You are a unified extraction system for a personal reminder agent that handles both user configuration and schedule creation.

Expected JSON Schema:
{
  "config": {
    "full_instruction_prompt": "string",
    "message_limit": "number",
    "timezone": "string"
  },
  "schedule": {
    "name": "string",
    "schedule_type": "string",
    "schedule_value": "object",
    "timezone": "string",
    "reminder_content_prompt_id": "string",
    "notes": "string"
  }
}

User Input: Set up daily reminders about Python programming at 9 AM with a professional tone

JSON Output:"""
    
    print("📝 Test Prompt:")
    print(test_prompt)
    print("\n🔄 Calling Gemini API...")
    
    try:
        response, context = await get_gemini_response_async(test_prompt)
        print(f"✅ Raw Response: {response}")
        print(f"📊 Context: {context}")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_unified_parsing():
    """Test the unified parsing function"""
    print("\n🔍 TESTING: Unified Parsing Function")
    print("=" * 50)
    
    test_input = "i want to learn pytorch daily and i want it on 5:35 pm at evening, notes: keep tone witty"
    test_user_id = "debug_user_123"
    
    print(f"📝 Test Input: {test_input}")
    print(f"👤 Test User ID: {test_user_id}")
    
    try:
        result = await parse_schedule_parameters_and_clarify(test_input, test_user_id)
        print(f"✅ Result: {result}")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main debug function"""
    print("🚀 DEBUGGING: Unified Config+Schedule LLM Integration")
    print("=" * 60)
    
    # Test 1: Direct LLM call
    llm_success = await test_direct_llm_call()
    
    # Test 2: Unified parsing
    if llm_success:
        parsing_success = await test_unified_parsing()
    else:
        print("⏭️ Skipping parsing test due to LLM failure")
        parsing_success = False
    
    print("\n" + "=" * 60)
    if llm_success and parsing_success:
        print("✅ ALL TESTS PASSED - Integration should work")
    else:
        print("❌ TESTS FAILED - Need to fix the integration")
    
    return 0 if (llm_success and parsing_success) else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
