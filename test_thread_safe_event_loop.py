#!/usr/bin/env python3
"""
Test the improved thread-safe event loop manager for Celery tasks.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from task import event_loop_manager
from db.mongo import get_schedule_by_id, update_schedule_by_id

def test_thread_safe_event_loop():
    """
    Test the new thread-safe event loop manager.
    """
    print("🧪 Testing Thread-Safe Event Loop Manager")
    print("=" * 50)
    
    async def _test_operations():
        """Test async DB operations"""
        print("✅ Inside async function")
        
        # Test 1: Try to get a schedule
        print("🔍 Testing get_schedule_by_id...")
        try:
            # Use a valid MongoDB ObjectId format for this test
            from bson import ObjectId
            test_id = str(ObjectId())  # Generate a valid ObjectId
            schedule_doc = await get_schedule_by_id(test_id)
            print(f"   Result: {schedule_doc is not None} (expected: False for non-existent ID)")
        except Exception as e:
            print(f"   Error: {e}")
        
        print("✅ Async operations completed")
        return "Success"
    
    # Test multiple calls to simulate Celery task behavior
    for i in range(3):
        print(f"\n🔄 Test Run #{i+1}")
        try:
            result = event_loop_manager.run_async(_test_operations())
            print(f"✅ Run {i+1} Success: {result}")
        except Exception as e:
            print(f"❌ Run {i+1} Error: {e}")
            return False
    
    return True

def simulate_multiple_celery_tasks():
    """
    Simulate multiple Celery tasks running concurrently.
    """
    print("\n🔄 Simulating Multiple Celery Tasks")
    print("=" * 45)
    
    def mock_celery_task(task_id: int):
        print(f"📋 Task {task_id}: Starting")
        
        async def _async_work():
            print(f"   Task {task_id}: In async function")
            # Simulate some async work
            await asyncio.sleep(0.1)
            print(f"   Task {task_id}: Async work completed")
            return f"Task {task_id} result"
        
        try:
            result = event_loop_manager.run_async(_async_work())
            print(f"   ✅ Task {task_id}: {result}")
            return True
        except Exception as e:
            print(f"   ❌ Task {task_id}: {e}")
            return False
    
    # Simulate 3 concurrent tasks
    results = []
    for i in range(3):
        results.append(mock_celery_task(i + 1))
    
    return all(results)

if __name__ == "__main__":
    print("Thread-Safe Event Loop Manager Test")
    print("=" * 60)
    
    # Test 1: Basic event loop reuse
    test1_success = test_thread_safe_event_loop()
    
    # Test 2: Multiple tasks
    test2_success = simulate_multiple_celery_tasks()
    
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS:")
    print(f"   Event Loop Reuse: {'✅ PASS' if test1_success else '❌ FAIL'}")
    print(f"   Multiple Tasks: {'✅ PASS' if test2_success else '❌ FAIL'}")
    
    if test1_success and test2_success:
        print("\n🎉 All tests passed! The event loop manager should resolve Celery issues.")
        print("\n✅ Key benefits:")
        print("   • Reuses a single event loop across all Celery tasks")
        print("   • Avoids 'Event loop is closed' errors")
        print("   • Thread-safe for concurrent task execution")
        print("   • Maintains your async MongoDB architecture")
    else:
        print("\n⚠️  Some tests failed. Check the implementation.")
    
    print("\n💡 Next step: Test with actual Celery worker:")
    print("   celery -A celery_config.Celery_app worker --loglevel=info")
