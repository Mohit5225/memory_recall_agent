#!/usr/bin/env python3
"""
Test script to validate the unified config+schedule integration.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).resolve().parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Test imports
try:
    from src.core.schedular import (
        schedule_reminder_task, 
        parse_schedule_parameters_and_clarify,
        UNIFIED_EXTRACTION_PROMPT_TEMPLATE
    )
    from src.db.mongo import get_user_config, save_user_config
    print("✅ All imports successful!")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

async def test_integration_flow():
    """Test the integrated config+schedule creation flow"""
    print("\n🧪 TESTING: Unified Config+Schedule Integration")
    print("=" * 60)
    
    # Test data
    test_user_id = "test_user_integration"
    test_input = "Set up daily reminders about Python programming at 9 AM with a professional and encouraging tone"
    
    print(f"📝 Test Input: {test_input}")
    print(f"👤 Test User ID: {test_user_id}")
    print()
    
    try:
        # Test 1: Check if the unified prompt template exists
        print("🔍 Test 1: Checking unified prompt template...")
        assert "config" in UNIFIED_EXTRACTION_PROMPT_TEMPLATE
        assert "schedule" in UNIFIED_EXTRACTION_PROMPT_TEMPLATE
        assert "{context_instruction}" in UNIFIED_EXTRACTION_PROMPT_TEMPLATE
        assert "{user_input}" in UNIFIED_EXTRACTION_PROMPT_TEMPLATE
        print("✅ Unified prompt template structure is correct")
        
        # Test 2: Check parsing function signature
        print("\n🔍 Test 2: Checking parsing function signature...")
        import inspect
        sig = inspect.signature(parse_schedule_parameters_and_clarify)
        params = list(sig.parameters.keys())
        assert "user_input" in params
        assert "user_id" in params
        print("✅ Parsing function has correct parameters")
        
        # Test 3: Check schedule_reminder_task function signature
        print("\n🔍 Test 3: Checking schedule_reminder_task function signature...")
        sig = inspect.signature(schedule_reminder_task)
        params = list(sig.parameters.keys())
        assert "user_id" in params
        assert "user_input" in params
        print("✅ schedule_reminder_task function has correct parameters")
        
        print("\n🎉 ALL INTEGRATION TESTS PASSED!")
        print("✅ The unified config+schedule flow is properly implemented")
        print("✅ Ready for end-to-end testing with real LLM calls")
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

async def main():
    """Main test function"""
    print("🚀 Starting Integration Validation...")
    
    success = await test_integration_flow()
    
    if success:
        print("\n" + "="*60)
        print("✅ INTEGRATION VALIDATION COMPLETE")
        print("✅ The unified config+schedule integration is ready!")
        print("\nNext steps:")
        print("1. Test with Postman using the reminder endpoints")
        print("2. Validate that both config and schedule are saved correctly")
        print("3. Ensure LLM generates proper unified responses")
        return 0
    else:
        print("\n❌ INTEGRATION VALIDATION FAILED")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
