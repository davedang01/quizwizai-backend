# Quiz Wiz AI Backend

A complete FastAPI-based backend for an AI-powered study application with built-in authentication, content scanning, test generation, grading, and progress tracking.

## Overview

Quiz Wiz AI Backend provides a robust REST API for:
- User authentication (email/password with bcrypt hashing)
- Content analysis (images and PDFs)
- Intelligent test generation with multiple question types
- Automated answer grading
- Progress tracking with achievement badges
- Secure session management with HTTPOnly cookies

## Quick Start

### Installation

```bash
# Clone and navigate to backend directory
cd /sessions/modest-magical-knuth/mnt/QuizWizAI/backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env

# Start MongoDB (if not running)
mongod &

# Start the server
uvicorn app.main:app --reload
```

Server runs at `http://localhost:8000`

### Interactive API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Architecture

### Core Components

```
app/
├── main.py              # FastAPI application, CORS, lifespan, routes
├── config.py            # Environment configuration
├── database.py          # MongoDB connections & collections
├── dependencies.py      # Authentication dependency injection
├── routers/             # Endpoint handlers
│   ├── auth.py         # User signup, login, logout, profile
│   ├── scan.py         # Content analysis (images, PDFs)
│   ├── tests.py        # Test generation, submission, grading
│   ├── results.py      # Result retrieval
│   └── progress.py     # User statistics & badges
└── services/
    └── ai_stub.py      # Stubbed AI service with realistic mock data
```

## Key Features

### 1. Authentication System

- **Email-based signup/login** with bcrypt password hashing
- **Secure session management** with 64-char random tokens
- **HTTPOnly cookies** preventing XSS attacks
- **Automatic expiry** (7 days, configurable)
- **Database-backed sessions** in MongoDB

```python
# Example: Login
POST /api/auth/login
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

### 2. Content Scanning

- **Image analysis** - Process lists of base64-encoded images
- **PDF analysis** - Extract and analyze PDF documents
- **Metadata extraction** - Subject, topics, difficulty level
- **Content preservation** - Store original extracted text

```python
# Example: Analyze Images
POST /api/scan/analyze
{
  "images_base64": ["iVBORw0KGgoAAAANSUhEUg..."]
}
```

### 3. Intelligent Test Generation

Supports multiple question types:
- **Multiple Choice** - 4 options with one correct answer
- **Word Problems** - Text-based mathematical problems
- **Math Problems** - Algebraic and numerical problems
- **Fill in the Blank** - Sentence completion
- **Mixed** - Combination of all types

Configurable parameters:
- Test name and type
- Difficulty level (Easy, Medium, Hard)
- Number of questions
- Additional custom prompts

```python
# Example: Generate Test
POST /api/tests/generate
{
  "scan_id": "550e8400-e29b-41d4-a716-446655440000",
  "test_name": "Math Chapter 3",
  "test_type": "Multiple Choice",
  "difficulty": "Medium",
  "num_questions": 10,
  "additional_prompts": "Focus on fractions"
}
```

### 4. Answer Grading

- **Case-insensitive comparison** for text answers
- **Numeric accuracy** for math problems
- **Instant feedback** with detailed analytics
- **Score calculation** as percentage

```python
# Example: Submit Test
POST /api/tests/submit
{
  "test_id": "550e8400-e29b-41d4-a716-446655440001",
  "answers": [
    {"question_id": "q1", "answer": "3/4"},
    {"question_id": "q2", "answer": "45"}
  ]
}

# Response
{
  "score": 80.0,
  "num_correct": 4,
  "num_total": 5,
  "answers": [...]
}
```

### 5. Progress Tracking

- **Test statistics** - Total completed, average score
- **Activity tracking** - Streak days, scan counts
- **Achievement badges** - Earned based on milestones
- **Recent results** - Last 10 test completions

Available badges:
- 🎯 **First Test** - Complete your first test
- 🏆 **Test Master** - Complete 5 tests
- ⭐ **High Scorer** - Achieve 80%+ average
- 🔥 **Streak Warrior** - Maintain 3-day streak

```python
# Example: Get Progress
GET /api/progress/stats

# Response
{
  "total_tests": 5,
  "avg_score": 82.4,
  "total_scans": 3,
  "streak_days": 2,
  "badges": [...],
  "recent_results": [...]
}
```

## Data Models

### User
```python
{
  "_id": "uuid",
  "name": "John Doe",
  "email": "john@example.com",
  "password_hash": "bcrypt_hash",
  "created_at": "2024-03-14T10:30:00",
  "updated_at": "2024-03-14T10:30:00"
}
```

### Scan
```python
{
  "_id": "uuid",
  "user_id": "uuid",
  "content_text": "Extracted content...",
  "subject": "Mathematics",
  "topics": ["Fractions", "Decimals"],
  "difficulty": "Medium",
  "num_pages": 5,
  "source_type": "pdf|images",
  "created_at": "2024-03-14T10:35:00"
}
```

### Test
```python
{
  "_id": "uuid",
  "user_id": "uuid",
  "scan_id": "uuid",
  "test_name": "Fractions Quiz",
  "test_type": "Multiple Choice",
  "difficulty": "Medium",
  "questions": [...],
  "is_completed": false,
  "score": null,
  "created_at": "2024-03-14T10:40:00"
}
```

### Result
```python
{
  "_id": "uuid",
  "user_id": "uuid",
  "test_id": "uuid",
  "score": 80.0,
  "num_correct": 4,
  "num_total": 5,
  "answers": [
    {
      "question_id": "q1",
      "user_answer": "3/4",
      "correct_answer": "3/4",
      "is_correct": true
    }
  ],
  "created_at": "2024-03-14T10:45:00"
}
```

## API Endpoints

### Authentication
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/auth/signup` | Create new user account |
| POST | `/api/auth/login` | Authenticate user |
| GET | `/api/auth/me` | Get current user |
| POST | `/api/auth/logout` | Clear session |

### Scanning
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/scan/analyze` | Analyze images |
| POST | `/api/scan/analyze-pdf` | Analyze PDF |

### Tests
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/tests/generate` | Create new test |
| GET | `/api/tests` | List user's tests |
| GET | `/api/tests/{test_id}` | Get specific test |
| DELETE | `/api/tests/{test_id}` | Delete test |
| POST | `/api/tests/{test_id}/reset` | Reset test |
| POST | `/api/tests/submit` | Submit and grade test |

### Results
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/results/{result_id}` | Get result by ID |
| GET | `/api/results/test/{test_id}` | Get result for test |

### Progress
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/progress/stats` | Get user statistics |

## Configuration

Environment variables (`.env`):

```
MONGO_URL=mongodb://localhost:27017
DB_NAME=quizwizai
SECRET_KEY=your-secret-key-here
ANTHROPIC_API_KEY=your-api-key-here
```

**Default values work for local development.**

## Database

### Collections

- `users` - User accounts and credentials
- `user_sessions` - Active sessions with 7-day expiry
- `scans` - Analyzed content documents
- `tests` - Generated test templates
- `results` - Completed test results and scores

All collections include indexes on `user_id` for efficient data isolation.

## Security Features

✅ **Password Hashing** - bcrypt with salt
✅ **Session Tokens** - 64-char random hex strings
✅ **HTTPOnly Cookies** - XSS protection
✅ **User Data Isolation** - All queries filtered by user_id
✅ **CORS Configuration** - Restricted to localhost:5173
✅ **Secure Defaults** - Secure=True, SameSite=lax

## Error Handling

Consistent error responses:

```python
{
  "detail": "Error message"
}
```

Status codes:
- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `404` - Not Found
- `500` - Server Error

## Testing

### With cURL
```bash
# Signup
curl -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice",
    "email": "alice@example.com",
    "password": "Pass123!"
  }' -c cookies.txt

# Get current user
curl http://localhost:8000/api/auth/me -b cookies.txt
```

### With Python
```python
import requests

session = requests.Session()

# Signup
session.post("http://localhost:8000/api/auth/signup", json={
    "name": "Alice",
    "email": "alice@example.com",
    "password": "Pass123!"
})

# Get stats
response = session.get("http://localhost:8000/api/progress/stats")
print(response.json())
```

## Development Notes

### Stubbed AI Service

The `app/services/ai_stub.py` provides realistic mock data without requiring Claude API:

- Question generation with varied types
- Content analysis with realistic metadata
- Answer grading with simple comparison
- Study guide generation

This allows full testing and development without API costs.

### Adding New Features

1. Define Pydantic models in router file
2. Implement endpoint handlers
3. Use `get_current_user` dependency for auth
4. Filter queries by `user_id` always
5. Use UUID for IDs, ISO 8601 for timestamps

### Database Queries

Always filter by user_id:

```python
await collection.find_one({"_id": id, "user_id": current_user["_id"]})
```

## Troubleshooting

### MongoDB Connection Failed
```bash
# Start MongoDB
mongod &

# Or with Homebrew (macOS)
brew services start mongodb-community
```

### Port Already in Use
```bash
# Use different port
uvicorn app.main:app --port 8001

# Or kill existing process
lsof -ti:8000 | xargs kill -9
```

### CORS Errors
Add frontend URL to `CORS` allowed_origins in `app/main.py`

### Import Errors
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

## Documentation

- **SETUP.md** - Installation and running instructions
- **API_TESTING.md** - Comprehensive endpoint testing guide
- **Interactive Docs** - http://localhost:8000/docs (Swagger UI)

## Production Checklist

- [ ] Change `SECRET_KEY` in `.env`
- [ ] Update `ANTHROPIC_API_KEY`
- [ ] Configure production MongoDB URL
- [ ] Update CORS allowed origins
- [ ] Set `secure=True` for HTTPS
- [ ] Enable rate limiting
- [ ] Setup logging and monitoring
- [ ] Add request validation middleware
- [ ] Enable database backups
- [ ] Setup error tracking (Sentry, etc.)

## License

Proprietary - Quiz Wiz AI

## Support

For issues or questions:
1. Check documentation in SETUP.md and API_TESTING.md
2. Review FastAPI docs: https://fastapi.tiangolo.com
3. Check MongoDB docs: https://docs.mongodb.com
4. Open issue if needed
