#!/usr/bin/env python3
"""
Phase 1 Test: Unified LLM Schema Testing
Tests the new unified extraction prompt that handles both scheduling and config.
"""

import asyncio
import json
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.llm.gemini import get_gemini_response_async
from src.core.schedular import SCHEDULING_EXTRACTION_PROMPT_TEMPLATE

async def test_unified_schema():
    """Test the new unified LLM schema with various user inputs."""
    
    test_cases = [
        {
            "name": "Schedule Only",
            "input": "Schedule a daily AI update reminder at 9 AM IST",
            "expected_config": False
        },
        {
            "name": "Schedule + Config",
            "input": "Remind me weekly every Tuesday at 3pm PST about team sync meetings, but make the reminders witty and brief",
            "expected_config": True
        },
        {
            "name": "Complex Config",
            "input": "Remind me every 3 hours about Python programming tips, I want detailed code examples in a professional tone",
            "expected_config": True
        },
        {
            "name": "One-time Schedule Only",
            "input": "Schedule a one-time reminder for my project deadline on 2025-06-30 at 5 PM",
            "expected_config": False
        }
    ]
    
    print("🧪 Testing Phase 1: Unified LLM Schema")
    print("=" * 50)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['name']}")
        print(f"Input: {test_case['input']}")
        print("-" * 30)
        
        # Format the prompt
        prompt = SCHEDULING_EXTRACTION_PROMPT_TEMPLATE.format(user_input=test_case['input'])
        
        try:
            # Call LLM
            response, context = await get_gemini_response_async(prompt)
            
            if response is None:
                print(f"❌ LLM call failed: {context}")
                continue
              # Try to parse JSON (handle code block wrapping)
            try:
                # Clean response of markdown code blocks
                clean_response = response.strip()
                if clean_response.startswith('```json'):
                    clean_response = clean_response[7:]  # Remove ```json
                if clean_response.endswith('```'):
                    clean_response = clean_response[:-3]  # Remove ```
                clean_response = clean_response.strip()
                
                parsed_response = json.loads(clean_response)
                print(f"✅ Valid JSON received")
                
                # Check if structure matches expected schema
                if 'schedule' in parsed_response and 'user_config_updates' in parsed_response:
                    print(f"✅ Contains both 'schedule' and 'user_config_updates' sections")
                    
                    # Check config detection
                    has_config = parsed_response['user_config_updates'].get('has_config_preferences', False)
                    expected = test_case['expected_config']
                    
                    if has_config == expected:
                        print(f"✅ Config detection correct: {has_config}")
                    else:
                        print(f"⚠️ Config detection mismatch: got {has_config}, expected {expected}")
                    
                    # Print key extracted values
                    schedule = parsed_response['schedule']
                    config = parsed_response['user_config_updates']
                    
                    print(f"📅 Schedule: {schedule['name']} ({schedule['schedule_type']})")
                    if has_config:
                        print(f"⚙️ Config: Topic='{config.get('topic_preferences')}', Style='{config.get('style_preferences')}', Tone='{config.get('tone_preferences')}'")
                    
                else:
                    print(f"❌ Missing required schema sections")
                    
            except json.JSONDecodeError as e:
                print(f"❌ Invalid JSON: {e}")
                print(f"Raw response: {response[:200]}...")
                
        except Exception as e:
            print(f"❌ Test failed: {e}")
    
    print("\n" + "=" * 50)
    print("Phase 1 testing complete!")

if __name__ == "__main__":
    asyncio.run(test_unified_schema())
