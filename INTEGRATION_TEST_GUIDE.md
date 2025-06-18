# Full End-to-End Integration Test Guide

## Overview
This guide walks you through running the complete end-to-end integration test for the unified config+schedule creation feature.

## What the Integration Test Validates

### ✅ Core Functionality
1. **New User Flow**: When a new user creates a schedule, both config and schedule are created together
2. **Existing User Flow**: When an existing user creates a schedule, config is only updated if needed
3. **Unified LLM Processing**: Single LLM call handles both config and schedule extraction
4. **Database Operations**: Both config and schedule are saved correctly to MongoDB
5. **API Integration**: FastAPI endpoint processes requests through the complete agent graph
6. **Error Handling**: System gracefully handles edge cases and validation errors

### 🧪 Test Scenarios
- **Test 1**: New user creates daily vitamin reminder → Creates config + schedule
- **Test 2**: Existing user creates weekly appointment reminder → Reuses config, adds schedule  
- **Test 3**: User with different timezone → Updates config if needed
- **Test 4**: Error handling with vague/invalid inputs

## Prerequisites

### 1. Environment Setup
Make sure you have:
- Python 3.12+ installed
- All dependencies installed: `pip install -r requirements.txt`
- MongoDB running and accessible
- Environment variables configured (`.env` file)

### 2. Check Dependencies
```powershell
cd "c:\Users\mohit\Desktop\python\agent01_attempt"
pip install -r requirements.txt
```

### 3. Verify Environment Variables
Ensure your `.env` file contains:
```
GEMINI_API_KEY=your_actual_api_key
MONGO_URI=your_mongodb_connection_string
DB_NAME=your_database_name
```

## Running the Tests

### Option 1: Manual Two-Terminal Approach

**Terminal 1 - Start the Server:**
```powershell
cd "c:\Users\mohit\Desktop\python\agent01_attempt"
python start_server.py
```
Wait for the message: "Application startup complete."

**Terminal 2 - Run the Tests:**
```powershell
cd "c:\Users\mohit\Desktop\python\agent01_attempt"
python test_full_integration.py
```

### Option 2: Background Server Approach

**Start server in background:**
```powershell
cd "c:\Users\mohit\Desktop\python\agent01_attempt"
Start-Process python -ArgumentList "start_server.py" -WindowStyle Minimized
```

**Run tests:**
```powershell
python test_full_integration.py
```

## Expected Test Output

### 🟢 Successful Test Output
```
🚀 Starting Full Integration Tests
Test User ID: test_user_1703123456

============================================================
🧪 TEST 1: New User Schedule Creation
============================================================
🔄 Sending chat request: Remind me to take my vitamins every day at 9 AM EST
📨 Response: {'success': True, 'response': '✅ Perfect! I've set up your...', 'intent': 'schedule_creation'}
✅ Found user config: {'timezone': 'America/New_York', 'message_limit': 50, ...}
✅ Found 1 active schedules for user
✅ TEST 1 PASSED: New user config and schedule created successfully

============================================================
🧪 TEST 2: Existing User Additional Schedule
============================================================
🔄 Sending chat request: Set up a weekly reminder for my doctor appointment every Monday at 2 PM EST
📨 Response: {'success': True, 'response': '✅ Perfect! I've set up your...', 'intent': 'schedule_creation'}
✅ Found 2 active schedules for user
✅ TEST 2 PASSED: Additional schedule created, config handled correctly

============================================================
🧪 TEST 3: Different Timezone Config Update
============================================================
🔄 Sending chat request: Remind me to call my friend tomorrow at 8 PM PST
📨 Response: {'success': True, 'response': '✅ Perfect! I've set up your...', 'intent': 'schedule_creation'}
✅ TEST 3 PASSED: Timezone handling tested

============================================================
🧪 TEST 4: Error Handling
============================================================
✅ TEST 4 PASSED: Error handling tested

============================================================
📊 FINAL TEST SUMMARY
============================================================
✅ Final config exists: True
✅ Final schedule count: 3

🎉 ALL INTEGRATION TESTS PASSED!
```

### 🔴 Common Error Scenarios

**Server Not Running:**
```
❌ Cannot connect to FastAPI server. Please start the server with:
   python main.py
```

**Database Connection Issues:**
```
❌ Database error: Could not connect to MongoDB
```

**API Key Issues:**
```
❌ LLM integration failed: Invalid API key
```

## Troubleshooting

### 1. Server Won't Start
```powershell
# Check if port 8000 is already in use
netstat -an | findstr :8000

# If in use, kill the process or change port in start_server.py
```

### 2. MongoDB Connection Issues
```powershell
# Test MongoDB connection
python -c "from src.db.mongo import get_mongo_client; import asyncio; asyncio.run(get_mongo_client())"
```

### 3. Environment Variable Issues
```powershell
# Check environment variables
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('GEMINI_API_KEY:', bool(os.getenv('GEMINI_API_KEY'))); print('MONGO_URI:', bool(os.getenv('MONGO_URI')))"
```

### 4. Import Issues
```powershell
# Test imports
python -c "from src.core.schedular import schedule_reminder_task; print('✅ Imports working')"
```

## Manual Testing Alternative

If the automated test fails, you can manually test the API:

### Using curl (PowerShell):
```powershell
# Test health endpoint
curl http://localhost:8000/api/v1/health

# Test schedule creation
$body = @{
    user_id = "manual_test_user"
    message = "Remind me to take vitamins daily at 9 AM EST"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/chat" -Method POST -Body $body -ContentType "application/json"
```

### Using Python requests:
```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/chat",
    json={
        "user_id": "manual_test_user",
        "message": "Remind me to take vitamins daily at 9 AM EST"
    }
)
print(response.json())
```

## Validation Checklist

After running tests, verify:

- [ ] **Config Created**: New user has config in database
- [ ] **Schedule Created**: New user has active schedule in database  
- [ ] **Config Reused**: Existing user doesn't duplicate config unnecessarily
- [ ] **Multiple Schedules**: User can have multiple active schedules
- [ ] **Timezone Handling**: Config reflects timezone preferences correctly
- [ ] **Error Handling**: System gracefully handles invalid inputs
- [ ] **API Response**: FastAPI returns proper success/error responses
- [ ] **Database Consistency**: All data saved correctly in MongoDB

## Next Steps

If all tests pass:
1. ✅ **Integration Complete**: Unified config+schedule creation is working
2. 🚀 **Production Ready**: System can handle real user requests
3. 📊 **Monitor Performance**: Watch logs for any edge cases in production
4. 🧹 **Cleanup**: Remove test files if desired

If tests fail:
1. 🔍 **Check Logs**: Review detailed error messages
2. 🐛 **Debug Issues**: Use troubleshooting guide above
3. 🔧 **Fix Problems**: Address specific failures
4. 🔄 **Re-test**: Run tests again after fixes

## Files Created for Testing

- `test_full_integration.py` - Complete integration test suite
- `start_server.py` - Easy server startup script
- `INTEGRATION_TEST_GUIDE.md` - This guide

These can be kept for future regression testing or removed after validation.
