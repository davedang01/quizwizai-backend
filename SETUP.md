# Quiz Wiz AI Backend - Setup & Running Guide

## Prerequisites

- Python 3.10+
- MongoDB server running locally on `mongodb://localhost:27017`
- pip package manager

## Installation

### 1. Clone/Extract the project and navigate to backend

```bash
cd /sessions/modest-magical-knuth/mnt/QuizWizAI/backend
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Setup environment variables

```bash
cp .env.example .env
# Edit .env with your configuration
```

The default `.env` will work for local development:
- MongoDB at `mongodb://localhost:27017`
- Database name: `quizwizai`
- Secret key is set to a dev value (change in production)

### 5. Ensure MongoDB is running

```bash
# If using MongoDB locally, start the service:
# macOS with Homebrew:
brew services start mongodb-community

# Or start MongoDB directly:
mongod
```

## Running the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

- Interactive API docs: `http://localhost:8000/docs`
- Alternative API docs: `http://localhost:8000/redoc`
- Health check: `http://localhost:8000/health`

## API Endpoints

### Authentication (`/api/auth`)
- `POST /signup` - Create new user account
- `POST /login` - Login with email and password
- `GET /me` - Get current authenticated user
- `POST /logout` - Clear session

### Scanning (`/api/scan`)
- `POST /analyze` - Analyze images and extract content
- `POST /analyze-pdf` - Analyze PDF files

### Tests (`/api/tests`)
- `POST /generate` - Generate a new test from scan
- `GET /` - List all tests for current user
- `GET /{test_id}` - Get specific test
- `DELETE /{test_id}` - Delete a test
- `POST /{test_id}/reset` - Reset test progress
- `POST /submit` - Submit test answers and get scored

### Results (`/api/results`)
- `GET /{result_id}` - Get specific result
- `GET /test/{test_id}` - Get result for a test

### Progress (`/api/progress`)
- `GET /stats` - Get user progress statistics and badges

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app and routes
│   ├── config.py               # Settings and environment
│   ├── database.py             # MongoDB connections
│   ├── dependencies.py         # Authentication dependency
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py             # Authentication endpoints
│   │   ├── scan.py             # Content scanning endpoints
│   │   ├── tests.py            # Test generation and submission
│   │   ├── results.py          # Test result endpoints
│   │   └── progress.py         # User progress statistics
│   └── services/
│       ├── __init__.py
│       └── ai_stub.py          # Stubbed AI service with mock data
├── requirements.txt            # Python dependencies
├── .env.example               # Example environment configuration
└── SETUP.md                   # This file
```

## Key Features

### Authentication
- Email-based signup and login
- Bcrypt password hashing
- HTTPOnly session cookies (7-day expiry)
- Secure session token storage in MongoDB

### Content Scanning
- Support for image lists and PDF files
- Extracts content text and metadata
- Identifies subject, topics, and difficulty level

### Test Generation
- Multiple question types: Multiple Choice, Word Problems, Math Problems, Fill in the Blank, Mixed
- Configurable difficulty levels
- Stubbed AI service returns realistic mock data

### Test Submission & Grading
- Grade answers against correct answers
- Calculate scores and statistics
- Store detailed results with answer analysis

### Progress Tracking
- Calculate average scores
- Track activity streaks
- Earned badges based on achievements
- Recent results history

## Development Notes

### Stubbed AI Service
The `app/services/ai_stub.py` file contains realistic mock data generation for:
- Content analysis (text, subject, topics, difficulty)
- Question generation for various types
- Answer grading
- Study guide generation

This allows full functionality testing without calling Claude API.

### Data Isolation
All endpoints require authentication and filter queries by `user_id` for complete data isolation between users.

### Session Management
- Sessions stored in `user_sessions` collection
- 7-day expiry time set in configuration
- Cookie cleared on logout

## Testing with cURL

### Signup
```bash
curl -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "email": "john@example.com",
    "password": "securepassword123"
  }' \
  -c cookies.txt
```

### Login
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@example.com",
    "password": "securepassword123"
  }' \
  -c cookies.txt
```

### Get Current User
```bash
curl -X GET http://localhost:8000/api/auth/me \
  -b cookies.txt
```

### Analyze Images
```bash
curl -X POST http://localhost:8000/api/scan/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "images_base64": ["base64_encoded_image_data_here"]
  }' \
  -b cookies.txt
```

### Health Check
```bash
curl http://localhost:8000/health
```

## Troubleshooting

### MongoDB Connection Error
- Ensure MongoDB is running: `brew services list` (macOS)
- Check connection URL in `.env`
- Verify MongoDB is accessible at the configured URL

### Port Already in Use
- Change port in startup command: `--port 8001`
- Or kill the process: `lsof -ti:8000 | xargs kill -9`

### Module Import Errors
- Ensure you're in the virtual environment: `source venv/bin/activate`
- Reinstall requirements: `pip install -r requirements.txt`

### CORS Issues (Frontend)
- Ensure frontend URL is in `CORS` allowed origins in `app/main.py`
- Default: `http://localhost:5173` and `http://localhost:3000`
