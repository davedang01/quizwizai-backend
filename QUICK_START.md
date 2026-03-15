# Quiz Wiz AI Backend - Quick Start Guide

## 30-Second Setup

```bash
# 1. Install dependencies
cd /sessions/modest-magical-knuth/mnt/QuizWizAI/backend
pip install -r requirements.txt

# 2. Start MongoDB
mongod &

# 3. Run server
uvicorn app.main:app --reload

# 4. Open browser
# http://localhost:8000/docs
```

---

## What You Get

✅ **17 API Endpoints** - Complete CRUD operations
✅ **Authentication** - Email signup/login with bcrypt
✅ **Content Scanning** - Upload images or PDFs
✅ **Test Generation** - 5 question types
✅ **Answer Grading** - Automatic scoring
✅ **Progress Tracking** - Stats and badges
✅ **Interactive Docs** - Built-in Swagger UI

---

## Core Endpoints

### 1. Authentication
```bash
# Signup
curl -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"name":"John","email":"john@example.com","password":"Pass123!"}' \
  -c cookies.txt

# Get current user
curl http://localhost:8000/api/auth/me -b cookies.txt
```

### 2. Scan Content
```bash
# Analyze images
curl -X POST http://localhost:8000/api/scan/analyze \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"images_base64":["iVBORw0KGg..."]}'
```

### 3. Generate Test
```bash
# Create test from scan
curl -X POST http://localhost:8000/api/tests/generate \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "scan_id":"550e8400-e29b-41d4-a716-446655440000",
    "test_name":"Quiz 1",
    "test_type":"Multiple Choice",
    "difficulty":"Medium",
    "num_questions":5
  }'
```

### 4. Submit Test
```bash
# Grade answers
curl -X POST http://localhost:8000/api/tests/submit \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "test_id":"550e8400-e29b-41d4-a716-446655440001",
    "answers":[
      {"question_id":"q1","answer":"Paris"},
      {"question_id":"q2","answer":"45"}
    ]
  }'
```

### 5. Get Progress
```bash
# View stats and badges
curl http://localhost:8000/api/progress/stats -b cookies.txt
```

---

## File Structure

```
backend/
├── app/                          # Application code
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Settings
│   ├── database.py              # MongoDB connection
│   ├── dependencies.py          # Auth dependency
│   ├── routers/
│   │   ├── auth.py             # Login, signup, etc
│   │   ├── scan.py             # Image/PDF analysis
│   │   ├── tests.py            # Test generation
│   │   ├── results.py          # Result retrieval
│   │   └── progress.py         # Stats & badges
│   └── services/
│       └── ai_stub.py          # Mock AI data
├── requirements.txt            # Dependencies
├── .env.example               # Config template
├── README.md                  # Full docs
├── SETUP.md                   # Install guide
├── API_TESTING.md            # API examples
└── verify_setup.py           # Verification script
```

---

## Test Question Types

**Multiple Choice** - 4 options, one correct
```json
{
  "type": "multiple_choice",
  "text": "What is the capital of France?",
  "options": ["London", "Paris", "Berlin", "Madrid"],
  "correct_answer": "Paris"
}
```

**Word Problems** - Text-based
```json
{
  "type": "word_problem",
  "text": "John has 5 apples and Mary gives him 3. How many total?",
  "correct_answer": "8"
}
```

**Math Problems** - Equations
```json
{
  "type": "math",
  "text": "Solve: 2x + 5 = 13",
  "correct_answer": "4"
}
```

**Fill in the Blank** - Completion
```json
{
  "type": "fill_blank",
  "text": "The capital of Japan is _____.",
  "correct_answer": "Tokyo"
}
```

**Mixed** - Combination of all

---

## Database Schema (5 Collections)

**users** - User accounts
**user_sessions** - Active sessions (7-day expiry)
**scans** - Analyzed content
**tests** - Generated tests
**results** - Completed test results

---

## Progress Badges

🎯 **First Test** - Complete your first test
🏆 **Test Master** - Complete 5 tests
⭐ **High Scorer** - Achieve 80%+ average
🔥 **Streak Warrior** - Maintain 3-day streak

---

## Key Features

✨ **Email Authentication** - Signup/login with email
🔐 **Secure Passwords** - Bcrypt hashing
🍪 **Session Cookies** - HTTPOnly, 7-day expiry
📄 **Content Upload** - Images and PDFs
🧠 **AI Stub Service** - No API calls needed
📊 **Auto Grading** - Instant test results
📈 **Progress Tracking** - Stats and badges
⚡ **Async/Await** - High performance
🎯 **Type Safe** - Type hints throughout

---

## Environment Variables

```
MONGO_URL=mongodb://localhost:27017
DB_NAME=quizwizai
SECRET_KEY=dev-key-change-production
ANTHROPIC_API_KEY=sk-placeholder
```

**All defaults configured for local development**

---

## Common Tasks

### Verify Setup
```bash
python verify_setup.py
```

### View API Documentation
```
http://localhost:8000/docs
```

### Check Server Health
```bash
curl http://localhost:8000/health
```

### List All Tests
```bash
curl http://localhost:8000/api/tests -b cookies.txt
```

### Reset a Test
```bash
curl -X POST http://localhost:8000/api/tests/{test_id}/reset \
  -b cookies.txt
```

### Delete a Test
```bash
curl -X DELETE http://localhost:8000/api/tests/{test_id} \
  -b cookies.txt
```

---

## Troubleshooting

**Can't connect to MongoDB?**
```bash
mongod &  # Start MongoDB
```

**Port 8000 in use?**
```bash
uvicorn app.main:app --port 8001
```

**Import errors?**
```bash
pip install -r requirements.txt --force-reinstall
```

**CORS errors?**
- Frontend must be at http://localhost:5173 or http://localhost:3000
- Check app/main.py CORS settings

---

## Next Steps

1. ✅ Install dependencies
2. ✅ Start MongoDB
3. ✅ Run the server
4. ✅ Open http://localhost:8000/docs
5. ✅ Test endpoints using Swagger UI
6. ✅ Review full docs in README.md

---

## Production Deployment

Before deploying to production:

- [ ] Change SECRET_KEY
- [ ] Update ANTHROPIC_API_KEY
- [ ] Use production MongoDB (Atlas)
- [ ] Update CORS origins
- [ ] Enable HTTPS
- [ ] Add rate limiting
- [ ] Configure backups
- [ ] Setup error tracking

---

## Support Files

- **README.md** - Full project documentation
- **SETUP.md** - Detailed installation guide
- **API_TESTING.md** - Complete API examples
- **PROJECT_SUMMARY.md** - Architecture overview
- **FILE_MANIFEST.txt** - File-by-file breakdown

---

**Ready to build?** 🚀

All 17 endpoints are implemented and tested. Start the server and explore the API docs at `/docs`.

For detailed guides, see README.md, SETUP.md, and API_TESTING.md.
