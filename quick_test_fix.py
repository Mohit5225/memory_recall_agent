#!/usr/bin/env python3
"""
Quick test for the fixed unified parsing.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).resolve().parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

async def test_fixed_parsing():
    """Test the fixed unified parsing"""
    try:
        from src.core.schedular import parse_schedule_parameters_and_clarify
        
        print("🔍 TESTING: Fixed Unified Parsing")
        print("=" * 50)
        
        test_input = "Set up daily reminders about Python programming at 9 AM with a professional tone"
        test_user_id = "test_user_fix"
        
        print(f"📝 Input: {test_input}")
        print(f"👤 User ID: {test_user_id}")
        print("\n🔄 Calling unified parsing...")
        
        result = await parse_schedule_parameters_and_clarify(test_input, test_user_id)
        
        print(f"✅ Result Status: {result.get('status')}")
        if result.get('status') == 'success':
            print(f"📋 Config: {result.get('config_data', {}).keys()}")
            print(f"📅 Schedule: {result.get('schedule_params', {}).keys()}")
        elif result.get('status') == 'failure':
            print(f"❌ Error: {result.get('message')}")
        else:
            print(f"⚠️ Needs clarification: {result.get('question')}")
            
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_fixed_parsing())
    print(f"\n{'✅ Test passed!' if success else '❌ Test failed!'}")
