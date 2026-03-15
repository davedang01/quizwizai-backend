# Quiz Wiz AI - Phase 2 Backend Endpoints

## Overview
Phase 2 adds 3 new routers with 13 endpoints for flashcards, study guides, and AI tutoring functionality.

## File Structure
```
app/
├── main.py                    # Updated with new router imports
├── database.py                # Updated with 3 new collection helpers
├── services/
│   └── ai_stub.py            # Updated with 3 new stub functions
└── routers/
    ├── flashcards.py         # NEW: Flashcard management (5 endpoints)
    ├── study_guides.py       # NEW: Study guide generation (3 endpoints)
    └── tutor.py              # NEW: AI tutoring sessions (5 endpoints)
```

## Endpoints

### Flashcards (`/api/flashcards`)
- `POST /generate` - Generate deck from scan (num_cards: 5-30)
- `POST /manual` - Create manual deck
- `GET /` - List all decks (sorted by timestamp)
- `GET /{deck_id}` - Get specific deck
- `DELETE /{deck_id}` - Delete deck

### Study Guides (`/api/study-guides`)
- `POST /generate` - Generate from test result ID
- `GET /{guide_id}` - Get specific guide
- `GET /result/{result_id}` - Check if guide exists for result

### Tutor (`/api/homework`)
- `POST /chat` - Send message (auto-creates session if needed)
- `GET /sessions` - List all sessions
- `GET /sessions/{session_id}` - Get session with messages
- `POST /sessions/new` - Create empty session
- `DELETE /sessions/{session_id}` - Delete session

## Key Features
- All endpoints require authentication (`get_current_user`)
- All data is filtered by `user_id` (user isolation)
- Realistic stub AI responses with variations
- Complete error handling and validation
- MongoDB collections: `flashcards`, `study_guides`, `homework_sessions`

## Testing
All files compile successfully:
```bash
python3 -m py_compile app/routers/flashcards.py app/routers/study_guides.py app/routers/tutor.py
```

All routers import successfully:
```bash
python3 -c "from app.routers import flashcards, study_guides, tutor; print('OK')"
```

Main app loads with 33 total routes (including Phase 1):
```bash
python3 -c "from app.main import app; print(f'{len([r for r in app.routes])} routes loaded')"
```
