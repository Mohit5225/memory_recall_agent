#!/usr/bin/env python3

import asyncio
import sys
import logging
from datetime import datetime, timezone, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def check_schedules():
    """Check what schedules are in the database and their status."""
    try:
        from src.db.mongo import get_schedule_collection, find_schedules_for_dispatch
        
        print("🔍 CHECKING DATABASE SCHEDULES")
        print("=" * 50)
        
        # Get all schedules
        collection = await get_schedule_collection()
        all_schedules = await collection.find({}).to_list(length=None)
        
        print(f"📊 Total schedules in database: {len(all_schedules)}")
        
        if all_schedules:
            print("\n📋 ALL SCHEDULES:")
            for i, schedule in enumerate(all_schedules):
                print(f"  {i+1}. ID: {schedule['_id']}")
                print(f"     Name: {schedule.get('name', 'N/A')}")
                print(f"     Status: {schedule.get('status', 'N/A')}")
                print(f"     Type: {schedule.get('schedule_type', 'N/A')}")
                print(f"     Next run: {schedule.get('next_run_at', 'N/A')}")
                print(f"     Last run: {schedule.get('last_run_at', 'N/A')}")
                print(f"     User ID: {schedule.get('user_id', 'N/A')}")
                print()
        
        # Check schedules due for dispatch
        print("🎯 SCHEDULES DUE FOR DISPATCH:")
        now_utc = datetime.now(timezone.utc)
        print(f"Current time (UTC): {now_utc.isoformat()}")
        
        due_schedules = await find_schedules_for_dispatch()
        print(f"Schedules due now: {len(due_schedules)}")
        
        if due_schedules:
            for i, schedule in enumerate(due_schedules):
                print(f"  {i+1}. {schedule['name']} (ID: {schedule['_id']}) - Next: {schedule.get('next_run_at')}")
        
        # Check schedules due in the next hour (for testing)
        future_time = now_utc + timedelta(hours=1)
        future_due = await find_schedules_for_dispatch(future_time)
        print(f"Schedules due within 1 hour: {len(future_due)}")
        
        if future_due:
            for i, schedule in enumerate(future_due):
                print(f"  {i+1}. {schedule['name']} (ID: {schedule['_id']}) - Next: {schedule.get('next_run_at')}")
        
        return all_schedules, due_schedules
        
    except Exception as e:
        logger.error(f"Error checking schedules: {e}", exc_info=True)
        return [], []

async def test_reminder_task():
    """Test the reminder task with a specific schedule ID if available."""
    try:
        all_schedules, due_schedules = await check_schedules()
        
        if all_schedules:
            # Pick the first schedule for testing
            test_schedule_id = str(all_schedules[0]['_id'])
            print(f"\n🧪 TESTING REMINDER TASK with schedule ID: {test_schedule_id}")
            
            # Import and run the reminder task
            from src.task import send_reminder_notification
            print("Executing send_reminder_notification task...")
            
            # This will run synchronously since it's a Celery task
            result = send_reminder_notification(test_schedule_id)
            print(f"Task executed successfully: {result}")
            
        else:
            print("❌ No schedules found to test with")
            
    except Exception as e:
        logger.error(f"Error testing reminder task: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(check_schedules())
    print("\n" + "="*50)
    print("Manual task test (uncomment to run):")
    # asyncio.run(test_reminder_task())
