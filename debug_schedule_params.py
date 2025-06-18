#!/usr/bin/env python3
"""
Debug script to check if schedule_params has user_id field
"""

import asyncio
import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from core.schedular import parse_schedule_parameters_and_clarify
from models.schedule import Schedule

async def debug_schedule_params():
    """Test schedule params creation"""
    
    # Test data - same as in the failing test
    user_id = "test_user_123"
    user_input = "Remind me to drink water every 2 hours during work days"
    user_timezone_str = "America/New_York"
    
    print(f"🔄 Testing with user_id: {user_id}")
    print(f"🔄 Testing with input: {user_input}")
    
    try:
        # Call the function
        result = await parse_schedule_parameters_and_clarify(
            user_id, user_input, user_timezone_str
        )
        
        print(f"✅ Function returned: {result['status']}")
        
        if result["status"] == "success":
            schedule_params = result["schedule_params"]
            print(f"📋 Schedule params keys: {list(schedule_params.keys())}")
            print(f"📋 Has user_id: {'user_id' in schedule_params}")
            if 'user_id' in schedule_params:
                print(f"📋 user_id value: {schedule_params['user_id']}")
            
            # Try to create Schedule object
            print("🔄 Attempting to create Schedule object...")
            schedule_obj = Schedule(**schedule_params)
            print(f"✅ Successfully created Schedule object with ID: {schedule_obj.user_id}")
        else:
            print(f"❌ Function failed with status: {result['status']}")
            print(f"❌ Message: {result.get('message', 'No message')}")
            
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_schedule_params())
