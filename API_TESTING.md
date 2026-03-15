# Quiz Wiz AI Backend - Complete API Testing Guide

This guide provides comprehensive examples for testing all endpoints using `curl`, Python, or via the interactive Swagger UI.

## Quick Start

1. Start the server:
   ```bash
   uvicorn app.main:app --reload
   ```

2. Access interactive API docs at: `http://localhost:8000/docs`

## Testing with cURL

### Helper: Save Cookies
For authenticated endpoints, use `-c` to save cookies and `-b` to send them:

```bash
curl -c cookies.txt          # Save response cookies to file
curl -b cookies.txt          # Send saved cookies
```

## Authentication Endpoints

### 1. Signup

**Request:**
```bash
curl -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice Smith",
    "email": "alice@example.com",
    "password": "SecurePass123!"
  }' \
  -c cookies.txt
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Alice Smith",
  "email": "alice@example.com",
  "created_at": "2024-03-14T10:30:00.000000"
}
```

**Note:** Session cookie is automatically set in `cookies.txt`

### 2. Login

**Request:**
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "password": "SecurePass123!"
  }' \
  -c cookies.txt
```

**Response:** Same as signup

### 3. Get Current User

**Request:**
```bash
curl -X GET http://localhost:8000/api/auth/me \
  -b cookies.txt
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Alice Smith",
  "email": "alice@example.com",
  "created_at": "2024-03-14T10:30:00.000000"
}
```

### 4. Logout

**Request:**
```bash
curl -X POST http://localhost:8000/api/auth/logout \
  -b cookies.txt
```

**Response:**
```json
{
  "message": "Logged out successfully"
}
```

## Scanning Endpoints

### 1. Analyze Images

**Request:**
```bash
curl -X POST http://localhost:8000/api/scan/analyze \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "images_base64": [
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    ]
  }'
```

**Response:**
```json
{
  "id": "660f8400-e29b-41d4-a716-446655440001",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "content_text": "This is extracted content from the uploaded material about Mathematics including fundamental concepts and practical applications.",
  "subject": "Mathematics",
  "topics": ["Fractions", "Decimals", "Word Problems"],
  "difficulty": "Medium",
  "num_pages": 3,
  "created_at": "2024-03-14T10:35:00.000000"
}
```

**Save scan_id for later use:**
```bash
SCAN_ID="660f8400-e29b-41d4-a716-446655440001"
```

### 2. Analyze PDF

**Request:**
```bash
curl -X POST http://localhost:8000/api/scan/analyze-pdf \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "pdf_base64": "JVBERi0xLjQKJeLj...",
    "filename": "math_textbook.pdf"
  }'
```

**Response:** Same structure as image analysis

## Test Endpoints

### 1. Generate Test

**Request:**
```bash
curl -X POST http://localhost:8000/api/tests/generate \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "scan_id": "660f8400-e29b-41d4-a716-446655440001",
    "test_name": "Fractions Quiz",
    "test_type": "Multiple Choice",
    "difficulty": "Medium",
    "num_questions": 5,
    "additional_prompts": "Focus on fraction operations"
  }'
```

**Response:**
```json
{
  "id": "770f8400-e29b-41d4-a716-446655440002",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "scan_id": "660f8400-e29b-41d4-a716-446655440001",
  "test_name": "Fractions Quiz",
  "test_type": "Multiple Choice",
  "difficulty": "Medium",
  "questions": [
    {
      "id": "q1",
      "type": "multiple_choice",
      "text": "What is 1/2 + 1/4?",
      "options": ["1/4", "3/4", "1/8", "2/4"],
      "difficulty": "Medium"
    },
    ...
  ],
  "is_completed": false,
  "score": null,
  "created_at": "2024-03-14T10:40:00.000000"
}
```

**Save test_id:**
```bash
TEST_ID="770f8400-e29b-41d4-a716-446655440002"
```

### 2. Get All Tests

**Request:**
```bash
curl -X GET http://localhost:8000/api/tests \
  -b cookies.txt
```

**Response:**
```json
[
  {
    "id": "770f8400-e29b-41d4-a716-446655440002",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "scan_id": "660f8400-e29b-41d4-a716-446655440001",
    "test_name": "Fractions Quiz",
    "test_type": "Multiple Choice",
    "difficulty": "Medium",
    "questions": [...],
    "is_completed": false,
    "score": null,
    "created_at": "2024-03-14T10:40:00.000000"
  },
  ...
]
```

### 3. Get Specific Test

**Request:**
```bash
curl -X GET http://localhost:8000/api/tests/$TEST_ID \
  -b cookies.txt
```

**Response:** Single test object (same structure as above)

### 4. Submit Test Answers

**Request:**
```bash
curl -X POST http://localhost:8000/api/tests/submit \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "test_id": "770f8400-e29b-41d4-a716-446655440002",
    "answers": [
      {
        "question_id": "q1",
        "answer": "3/4"
      },
      {
        "question_id": "q2",
        "answer": "45"
      },
      {
        "question_id": "q3",
        "answer": "Mercury"
      },
      {
        "question_id": "q4",
        "answer": "Au"
      },
      {
        "question_id": "q5",
        "answer": "William Shakespeare"
      }
    ]
  }'
```

**Response:**
```json
{
  "id": "880f8400-e29b-41d4-a716-446655440003",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "test_id": "770f8400-e29b-41d4-a716-446655440002",
  "score": 80.0,
  "num_correct": 4,
  "num_total": 5,
  "answers": [
    {
      "question_id": "q1",
      "user_answer": "3/4",
      "correct_answer": "3/4",
      "is_correct": true
    },
    ...
  ],
  "created_at": "2024-03-14T10:45:00.000000"
}
```

**Save result_id:**
```bash
RESULT_ID="880f8400-e29b-41d4-a716-446655440003"
```

### 5. Reset Test

**Request:**
```bash
curl -X POST http://localhost:8000/api/tests/$TEST_ID/reset \
  -b cookies.txt
```

**Response:**
```json
{
  "message": "Test reset successfully"
}
```

### 6. Delete Test

**Request:**
```bash
curl -X DELETE http://localhost:8000/api/tests/$TEST_ID \
  -b cookies.txt
```

**Response:**
```json
{
  "message": "Test deleted successfully"
}
```

## Results Endpoints

### 1. Get Result by ID

**Request:**
```bash
curl -X GET http://localhost:8000/api/results/$RESULT_ID \
  -b cookies.txt
```

**Response:**
```json
{
  "id": "880f8400-e29b-41d4-a716-446655440003",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "test_id": "770f8400-e29b-41d4-a716-446655440002",
  "score": 80.0,
  "num_correct": 4,
  "num_total": 5,
  "answers": [...],
  "created_at": "2024-03-14T10:45:00.000000"
}
```

### 2. Get Result by Test ID

**Request:**
```bash
curl -X GET http://localhost:8000/api/results/test/$TEST_ID \
  -b cookies.txt
```

**Response:** Same structure as above

## Progress Endpoints

### Get Progress Statistics

**Request:**
```bash
curl -X GET http://localhost:8000/api/progress/stats \
  -b cookies.txt
```

**Response:**
```json
{
  "total_tests": 3,
  "avg_score": 82.33,
  "total_scans": 2,
  "streak_days": 2,
  "badges": [
    {
      "id": "first_test",
      "name": "First Test",
      "description": "Completed your first test",
      "earned_at": "2024-03-12T10:00:00.000000"
    },
    {
      "id": "high_scorer",
      "name": "High Scorer",
      "description": "Achieved average score of 80% or higher",
      "earned_at": "2024-03-14T11:00:00.000000"
    }
  ],
  "recent_results": [
    {
      "test_id": "770f8400-e29b-41d4-a716-446655440002",
      "test_name": "Fractions Quiz",
      "score": 80.0,
      "created_at": "2024-03-14T10:45:00.000000"
    }
  ]
}
```

## Health Check

**Request:**
```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy"
}
```

## Testing with Python

```python
import requests
import json

BASE_URL = "http://localhost:8000"
cookies = {}

# Signup
signup_response = requests.post(
    f"{BASE_URL}/api/auth/signup",
    json={
        "name": "Alice Smith",
        "email": "alice@example.com",
        "password": "SecurePass123!"
    }
)
user_id = signup_response.json()["id"]
cookies = signup_response.cookies

# Analyze images
scan_response = requests.post(
    f"{BASE_URL}/api/scan/analyze",
    json={"images_base64": ["base64_data"]},
    cookies=cookies
)
scan_id = scan_response.json()["id"]

# Generate test
test_response = requests.post(
    f"{BASE_URL}/api/tests/generate",
    json={
        "scan_id": scan_id,
        "test_name": "Quiz 1",
        "test_type": "Multiple Choice",
        "difficulty": "Medium",
        "num_questions": 5
    },
    cookies=cookies
)
test_id = test_response.json()["id"]

# Get questions from test
test_data = test_response.json()
questions = test_data["questions"]

# Submit answers
submit_response = requests.post(
    f"{BASE_URL}/api/tests/submit",
    json={
        "test_id": test_id,
        "answers": [
            {"question_id": q["id"], "answer": q["correct_answer"]}
            for q in questions
        ]
    },
    cookies=cookies
)

result = submit_response.json()
print(f"Score: {result['score']}%")
print(f"Correct: {result['num_correct']}/{result['num_total']}")

# Get progress
progress_response = requests.get(
    f"{BASE_URL}/api/progress/stats",
    cookies=cookies
)
progress = progress_response.json()
print(f"Total Tests: {progress['total_tests']}")
print(f"Average Score: {progress['avg_score']}")
print(f"Badges: {len(progress['badges'])}")
```

## Common Errors and Solutions

### 401 Unauthorized
- Not authenticated or session expired
- Solution: Ensure cookie file exists and session hasn't expired

### 404 Not Found
- Resource doesn't exist or belongs to another user
- Solution: Verify IDs are correct and belong to current user

### 400 Bad Request
- Invalid input format
- Solution: Check JSON format and required fields

### MongoDB Connection Error
- Database not running
- Solution: Start MongoDB service

## Test Scenarios

### Complete User Journey

```bash
# 1. Signup
curl -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "email": "test@example.com",
    "password": "TestPass123!"
  }' \
  -c cookies.txt

# 2. Analyze content
SCAN_ID=$(curl -s -X POST http://localhost:8000/api/scan/analyze \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"images_base64": ["base64_data"]}' \
  | jq -r '.id')

# 3. Generate test
TEST_ID=$(curl -s -X POST http://localhost:8000/api/tests/generate \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d "{
    \"scan_id\": \"$SCAN_ID\",
    \"test_name\": \"Quiz\",
    \"test_type\": \"Multiple Choice\",
    \"difficulty\": \"Medium\",
    \"num_questions\": 5
  }" | jq -r '.id')

# 4. Submit test
curl -s -X POST http://localhost:8000/api/tests/submit \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d "{
    \"test_id\": \"$TEST_ID\",
    \"answers\": [
      {\"question_id\": \"q1\", \"answer\": \"correct_answer\"}
    ]
  }"

# 5. View progress
curl -s -X GET http://localhost:8000/api/progress/stats \
  -b cookies.txt | jq .
```
