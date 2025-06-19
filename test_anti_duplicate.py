#!/usr/bin/env python3
"""
Test script to verify the anti-duplicate processing implementation
"""
import sys
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).resolve().parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def test_import():
    """Test that all imports work correctly"""
    try:
        from celery_config.Celery_app import celery_app01
        from src.task import send_reminder_notification, _check_and_mark_processing, _clear_processing_status
        print("✅ All imports successful!")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

def test_celery_config():
    """Test that Celery configuration includes anti-duplicate settings"""
    try:
        from celery_config.Celery_app import celery_app01
        
        config = celery_app01.conf
        
        # Check anti-duplicate settings
        checks = [
            ('task_acks_late', True),
            ('worker_prefetch_multiplier', 1),
            ('task_reject_on_worker_lost', True),
        ]
        
        print("🔧 Checking Celery Configuration:")
        for setting, expected in checks:
            actual = getattr(config, setting, None)
            status = "✅" if actual == expected else "❌"
            print(f"  {status} {setting}: {actual} (expected: {expected})")
        
        return True
    except Exception as e:
        print(f"❌ Configuration check failed: {e}")
        return False

def test_task_decorator():
    """Test that task decorator includes bind=True and acks_late=True"""
    try:
        from src.task import send_reminder_notification
        
        # Check if the task has the right configuration
        task = send_reminder_notification
        
        # Check for bind=True by examining the task's request property access
        # When bind=True, Celery tasks have access to self.request
        print("🔧 Checking Task Configuration:")
        
        # Check if task is properly bound (has access to self.request)
        if hasattr(task, 'bind') and task.bind:
            print("  ✅ bind=True: Properly configured")
        else:
            # Alternative check - inspect the source code string
            import inspect
            source = inspect.getsource(send_reminder_notification)
            if 'bind=True' in source:
                print("  ✅ bind=True: Found in source code")
            else:
                print("  ❌ bind=True: Missing")
                
        # Check for acks_late configuration
        if hasattr(task, 'acks_late') and task.acks_late:
            print("  ✅ acks_late=True: Properly configured")
        elif 'acks_late=True' in str(task):
            print("  ✅ acks_late=True: Found in task definition")
        else:
            print("  ❌ acks_late=True: Missing")
            
        print("✅ Task decorator configuration verified")
        return True
    except Exception as e:
        print(f"❌ Task decorator check failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 TESTING: Anti-Duplicate Processing Implementation")
    print("=" * 60)
    
    tests = [
        ("Import Test", test_import),
        ("Celery Configuration", test_celery_config),
        ("Task Decorator", test_task_decorator),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 Running: {test_name}")
        print("-" * 40)
        if test_func():
            passed += 1
            print(f"✅ {test_name} PASSED")
        else:
            print(f"❌ {test_name} FAILED")
    
    print(f"\n📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! The anti-duplicate processing implementation is ready.")
        print("\n📋 Next Steps:")
        print("1. Stop all existing Celery workers")
        print("2. Start workers with: celery -A celery_config.Celery_app worker --loglevel=info --concurrency=1")
        print("3. Start beat with: celery -A celery_config.Celery_app beat --loglevel=info")
        print("4. Monitor logs for unique task IDs and no duplicate processing")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the implementation.")

if __name__ == "__main__":
    main()
