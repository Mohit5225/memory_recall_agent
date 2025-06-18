#!/usr/bin/env python3
"""
Simple Integration Test for Unified Config+Schedule Creation
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
import httpx
import json
import logging
import time

# Add the project root to sys.path
project_root = str(Path(__file__).resolve().parent)
if project_root not in sys.path:
    sys.path.append(project_root)

# Import functions to inspect database state
from src.db.mongo import get_user_config, find_schedules, get_mongo_client, close_mongo_client
from src.models.schedule import ScheduleStatus

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Test configuration
BASE_URL = "http://localhost:8000"
API_ENDPOINT = f"{BASE_URL}/api/v1/chat"

async def test_unified_integration():
    """Simple test of the unified config+schedule integration"""
    
    # Create unique test user
    test_user_id = f"test_user_{int(time.time() * 1000000)}"
    
    logger.info("🚀 UNIFIED INTEGRATION TEST")
    logger.info("=" * 50)
    logger.info(f"Test User: {test_user_id}")
    
    client = httpx.AsyncClient(timeout=30.0)
    
    try:
        # Check initial state
        logger.info("\n🔍 Checking initial state...")
        initial_config = await get_user_config(test_user_id)
        initial_schedules = await find_schedules(user_id=test_user_id, query_params={"status": ScheduleStatus.ACTIVE.value})
        
        logger.info(f"Initial config: {initial_config} (type: {type(initial_config)})")
        logger.info(f"Initial schedules: {len(initial_schedules)}")
        
        # Verify initial state (config should be empty string or None)
        if not (initial_config == "" or initial_config is None):
            logger.error(f"❌ User already has config: {initial_config}")
            return False
            
        if len(initial_schedules) > 0:
            logger.error(f"❌ User already has schedules: {len(initial_schedules)}")
            return False
            
        # Send schedule creation request
        logger.info("\n🔄 Creating schedule...")
        message = "Remind me to take my vitamins every day at 9 AM EST with a friendly and encouraging tone"
        
        payload = {"user_id": test_user_id, "message": message}
        logger.info(f"Sending: {payload}")
        
        response = await client.post(API_ENDPOINT, json=payload)
        response.raise_for_status()
        result = response.json()
        
        logger.info(f"📨 Response: {result}")
        
        # Check response
        if not result.get("success"):
            logger.error(f"❌ Request failed: {result}")
            return False
            
        # Check final state
        logger.info("\n🔍 Checking final state...")
        final_config = await get_user_config(test_user_id)
        final_schedules = await find_schedules(user_id=test_user_id, query_params={"status": ScheduleStatus.ACTIVE.value})
        
        logger.info(f"Final config: {final_config} (type: {type(final_config)})")
        logger.info(f"Final schedules: {len(final_schedules)}")
        
        # Verify final state
        success = True
        
        if not final_config or final_config == "":
            logger.error("❌ Config was not created")
            success = False
        else:
            logger.info("✅ Config was created")
            
        if len(final_schedules) == 0:
            logger.error("❌ Schedule was not created")
            success = False
        elif len(final_schedules) == 1:
            logger.info("✅ Schedule was created")
            schedule = final_schedules[0]
            logger.info(f"  - Name: {schedule.name}")
            logger.info(f"  - Type: {schedule.schedule_type}")
            logger.info(f"  - Status: {schedule.status}")
            logger.info(f"  - Next run: {schedule.next_run_at}")
        else:
            logger.warning(f"⚠️ Unexpected number of schedules: {len(final_schedules)}")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        await client.aclose()

async def main():
    """Main test function"""
    try:
        # Initialize MongoDB connection
        await get_mongo_client()
        
        # Run the test
        success = await test_unified_integration()
        
        if success:
            logger.info("\n🎉 INTEGRATION TEST PASSED!")
        else:
            logger.info("\n❌ INTEGRATION TEST FAILED!")
            
        return success
        
    finally:
        # Clean up MongoDB connection
        await close_mongo_client()

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
