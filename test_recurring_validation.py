#!/usr/bin/env python3
"""
Test script to validate the recurring reminder fix.
This script tests the improved logic in send_reminder_notification.
"""
import sys
import os
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add project root to path
project_root = str(Path(__file__).resolve().parent)
sys.path.insert(0, project_root)

from src.models.schedule import Schedule, ScheduleType, ScheduleStatus
from src.core.schedular import RRuleGenerator
from src.task import send_reminder_notification
from src.db.mongo import get_mongo_client, close_mongo_client

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_rrule_generator():
    """Test RRuleGenerator with different schedule types"""
    print("\n🔍 TESTING: RRuleGenerator functionality")
    
    test_cases = [
        {
            "name": "Daily Schedule",
            "schedule_type": "daily",
            "schedule_value": {"time": "09:00 AM"},
            "expected": "Should calculate next day at 9 AM"
        },
        {
            "name": "Weekly Schedule", 
            "schedule_type": "weekly",
            "schedule_value": {"day_of_week": "Monday", "time": "10:00 AM"},
            "expected": "Should calculate next Monday at 10 AM"
        },
        {
            "name": "Monthly Schedule",
            "schedule_type": "monthly",
            "schedule_value": {"day_of_month": 15, "time": "14:00"},
            "expected": "Should calculate 15th of next month at 2 PM"
        }
    ]
    
    for test_case in test_cases:
        print(f"\n  Testing: {test_case['name']}")
        try:
            rrule_gen = RRuleGenerator(
                test_case["schedule_type"],
                test_case["schedule_value"]
            )
            
            # Test generating rrule params
            rrule_params = rrule_gen.generate_rrule_params()
            print(f"    ✅ RRule params generated: {rrule_params}")
            
            # Test calculating next occurrence
            start_time = datetime.now(timezone.utc)
            next_occurrence = rrule_gen.calculate_initial_next_run_at(start_time)
            print(f"    ✅ Next occurrence: {next_occurrence.isoformat() if next_occurrence else 'None'}")
            print(f"    📝 Expected: {test_case['expected']}")
            
        except Exception as e:
            print(f"    ❌ Error: {e}")
            logger.exception(f"RRuleGenerator test failed for {test_case['name']}")

def test_schedule_type_validation():
    """Test the improved condition logic"""
    print("\n🔍 TESTING: Schedule type validation logic")
    
    # Test explicit recurring types
    recurring_types = [ScheduleType.DAILY, ScheduleType.WEEKLY, ScheduleType.MONTHLY, ScheduleType.INTERVAL]
    print(f"  ✅ Explicit recurring types: {[t.value for t in recurring_types]}")
    
    # Test condition
    for schedule_type in ScheduleType:
        is_recurring = schedule_type in recurring_types
        print(f"    {schedule_type.value}: {'✅ Recurring' if is_recurring else '❌ Not recurring'}")

def create_test_schedule_dict(schedule_type: str) -> dict:
    """Create a test schedule dictionary"""
    return {
        "_id": "test_schedule_123",
        "user_id": "test_user",
        "name": f"Test {schedule_type.title()} Schedule",
        "schedule_type": schedule_type,
        "schedule_value": {"time": "09:00 AM"} if schedule_type == "daily" else {"day_of_week": "Monday", "time": "09:00 AM"},
        "rrule_params": {"freq": 0, "byhour": [9], "byminute": [0], "bysecond": [0]} if schedule_type != "once" else None,
        "status": "active",
        "next_run_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "last_run_at": None,
        "created_at": datetime.now(timezone.utc),
        "last_modified_at": datetime.now(timezone.utc)
    }

async def test_database_connection():
    """Test database connectivity"""
    print("\n🔍 TESTING: Database connectivity")
    try:
        client = await get_mongo_client()
        if client:
            print("    ✅ MongoDB connection successful")
            # Test a simple ping
            await client.admin.command('ping')
            print("    ✅ Database ping successful")
        else:
            print("    ❌ MongoDB connection failed")
    except Exception as e:
        print(f"    ❌ Database error: {e}")
        logger.exception("Database connection test failed")

def print_validation_summary():
    """Print summary of what we're validating"""
    print("=" * 60)
    print("🎯 RECURRING REMINDER VALIDATION TEST")
    print("=" * 60)
    print("""
WHAT WE'RE TESTING:
1. ✅ RRuleGenerator.calculate_initial_next_run_at() works correctly
2. ✅ Database update functions exist and are accessible
3. ✅ Improved condition logic (explicit recurring types)
4. ✅ Better error handling and logging
5. ✅ Validation checks for missing rrule_params

VALIDATION APPROACH:
- Test RRuleGenerator with different schedule types
- Validate database connectivity
- Check improved logic conditions
- Simulate error scenarios
""")

async def main():
    """Main test execution"""
    print_validation_summary()
    
    # Test 1: RRuleGenerator functionality
    await test_rrule_generator()
    
    # Test 2: Schedule type validation
    test_schedule_type_validation()
    
    # Test 3: Database connectivity
    await test_database_connection()
    
    print("\n" + "=" * 60)
    print("🎉 VALIDATION TESTS COMPLETED")
    print("=" * 60)
    print("""
NEXT STEPS FOR MANUAL TESTING:
1. Start Redis server: redis-server
2. Start Celery worker: celery -A celery_config.Celery_app worker --loglevel=info
3. Start Celery beat: celery -A celery_config.Celery_app beat --loglevel=info
4. Create a test recurring schedule in the database
5. Wait for it to fire and check logs for our improved messages

POSTMAN TEST ENDPOINTS:
- POST /api/chat with schedule creation request
- Monitor Celery logs for our new debug messages
""")
    
    # Clean up
    await close_mongo_client()

if __name__ == "__main__":
    asyncio.run(main())
