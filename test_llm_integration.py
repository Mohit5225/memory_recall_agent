#!/usr/bin/env python3
"""
Test script to demonstrate LLM-powered reminder content generation.
This shows what the system will now actually generate for reminders.
"""
import sys
import asyncio
import logging
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).resolve().parent)
sys.path.insert(0, project_root)

from src.task import _generate_reminder_content
from src.db.mongo import get_mongo_client, close_mongo_client, save_user_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_llm_reminder_generation():
    """Test LLM-powered reminder content generation"""
    print("\n🧪 TESTING: LLM-Powered Reminder Content Generation")
    print("=" * 60)
    
    test_user_id = "test_user_llm_demo"
    
    # Test configuration for PyTorch reminders
    pytorch_config = """
# PyTorch Reminder Agent Configuration

# --- Core Function ---
# This agent generates brief, bite-sized PyTorch knowledge reminders.

# --- Reminder Topic ---
# Current Topic: PyTorch methods, functions, and best practices

# --- Reminder Style ---
# Style: Quick, practical, actionable tips
# Tone: Encouraging, expert-level but accessible
# Length: Max 2-3 sentences

# --- Format ---
# Always start with "Today's PyTorch tip:" 
# Focus on one specific method, function, or concept
# Include a brief practical use case or example

# --- Example ---
# "Today's PyTorch tip: torch.nn.functional.relu() is your go-to activation function for introducing non-linearity. Use it after linear layers: torch.nn.functional.relu(linear_output)."
"""
    
    try:
        # Connect to database
        await get_mongo_client()
        
        # Save test user configuration
        print(f"📝 Setting up test user config for {test_user_id}...")
        success = await save_user_config(test_user_id, pytorch_config)
        if not success:
            print("❌ Failed to save user config")
            return
        
        print("✅ User config saved successfully")
        
        # Test different reminder scenarios
        test_scenarios = [
            ("Daily PyTorch Study", "Review tensor operations"),
            ("Weekly Code Review", "Check model performance"),
            ("Monthly Learning Goal", None),  # No notes
        ]
        
        print("\n🔄 Generating LLM-powered reminder content...")
        print("-" * 40)
        
        for schedule_name, schedule_notes in test_scenarios:
            print(f"\n📅 Schedule: {schedule_name}")
            if schedule_notes:
                print(f"📝 Notes: {schedule_notes}")
            
            # Generate reminder content
            content = await _generate_reminder_content(
                user_id=test_user_id,
                schedule_name=schedule_name,
                schedule_notes=schedule_notes
            )
            
            print(f"💬 Generated Content:")
            print(f"   '{content}'")
            
        # Test fallback scenario (user with no config)
        print(f"\n🔧 Testing fallback for user with no config...")
        fallback_content = await _generate_reminder_content(
            user_id="nonexistent_user",
            schedule_name="Test Schedule",
            schedule_notes="Test notes"
        )
        print(f"💬 Fallback Content:")
        print(f"   '{fallback_content}'")
        
        print("\n✅ LLM reminder generation test completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        print(f"❌ Test failed: {e}")
    
    finally:
        await close_mongo_client()

async def demonstrate_system_capabilities():
    """Demonstrate what the fixed system can now do"""
    print("\n🎯 SYSTEM CAPABILITIES DEMONSTRATION")
    print("=" * 50)
    
    print("✅ BEFORE (Old System):")
    print("   Static: 'Reminder: Daily PyTorch Study - Notes: Review tensor operations'")
    
    print("\n✅ AFTER (Fixed System):")
    print("   Dynamic: 'Today's PyTorch tip: torch.tensor() creates tensors from data.'")
    print("   Dynamic: 'Today's PyTorch tip: Use torch.cuda.is_available() to check GPU.'")
    print("   Dynamic: 'Today's PyTorch tip: torch.nn.Module is the base class for all models.'")
    
    print("\n🔧 KEY IMPROVEMENTS:")
    print("   1. User-configurable topics and styles")
    print("   2. LLM-generated personalized content")
    print("   3. Fallback to static content if LLM fails")
    print("   4. Integration with existing scheduling system")
    print("   5. Robust error handling and logging")

if __name__ == "__main__":
    print("🚀 LLM REMINDER INTEGRATION DEMONSTRATION")
    print("=" * 60)
    
    # Run the demonstration
    asyncio.run(demonstrate_system_capabilities())
    
    # Run the actual test
    asyncio.run(test_llm_reminder_generation())
    
    print("\n📋 NEXT STEPS:")
    print("1. Run this test to see LLM integration in action")
    print("2. Set up user configs via the API")
    print("3. Create schedules and watch Celery logs for LLM-generated content")
    print("4. Replace SMS placeholder with real notification system")
