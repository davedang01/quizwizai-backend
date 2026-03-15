import uuid
import json
import logging
from datetime import datetime
from typing import List, Dict, Any

import anthropic

from ..config import get_settings

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"


def get_client() -> anthropic.AsyncAnthropic:
    settings = get_settings()
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


def _parse_json(text: str, fallback: Any = None) -> Any:
    """Attempt to parse JSON from Claude's response, handling markdown fences."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try stripping markdown code fences
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    # Try finding JSON array or object in the text
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

    return fallback


async def analyze_content(text_or_base64: str) -> Dict[str, Any]:
    """Use Claude to analyze uploaded study content and extract metadata."""
    client = get_client()

    # Truncate very long content to stay within token limits
    content_preview = text_or_base64[:4000]

    try:
        message = await client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Analyze the following study material. Respond with ONLY a JSON object, "
                        "no other text:\n"
                        '{"subject": "<subject area like Mathematics, Science, History, English, etc>",'
                        ' "topics": ["topic1", "topic2", "topic3"],'
                        ' "difficulty": "<Easy|Medium|Hard>",'
                        ' "content_text": "<2-3 sentence summary of what the material covers>"}\n\n'
                        f"Material:\n{content_preview}"
                    ),
                }
            ],
        )

        result = _parse_json(
            message.content[0].text,
            {
                "subject": "General",
                "topics": ["Study Material"],
                "difficulty": "Medium",
                "content_text": message.content[0].text[:500],
            },
        )
    except Exception as e:
        logger.error(f"Claude API error in analyze_content: {e}")
        result = {
            "subject": "General",
            "topics": ["Study Material"],
            "difficulty": "Medium",
            "content_text": "Content uploaded successfully. AI analysis is temporarily unavailable.",
        }

    return {
        "id": str(uuid.uuid4()),
        "content_text": result.get("content_text", ""),
        "subject": result.get("subject", "General"),
        "topics": result.get("topics", ["General"]),
        "difficulty": result.get("difficulty", "Medium"),
        "num_pages": 1,
        "created_at": datetime.utcnow().isoformat(),
    }


async def generate_questions(
    content_text: str, test_type: str, difficulty: str, num_questions: int
) -> List[Dict[str, Any]]:
    """Use Claude to generate test questions based on content."""
    client = get_client()

    type_instructions = {
        "Multiple Choice": (
            'multiple choice questions. Each must have "type": "multiple_choice", '
            '"text", "options" (array of 4 choices), and "correct_answer" (must match one option exactly).'
        ),
        "Word Problems": (
            'word problems. Each must have "type": "word_problem", "text", and "correct_answer" (a number or short phrase).'
        ),
        "Math Problems": (
            'math problems. Each must have "type": "math", "text", and "correct_answer" (a number).'
        ),
        "Fill in the Blank": (
            'fill-in-the-blank questions with a blank shown as ______. '
            'Each must have "type": "fill_blank", "text", and "correct_answer" (the word or phrase for the blank).'
        ),
    }

    instruction = type_instructions.get(
        test_type,
        (
            "a mix of multiple choice, word problems, math, and fill-in-the-blank questions. "
            "Use the appropriate type field for each."
        ),
    )

    try:
        message = await client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Generate exactly {num_questions} {instruction}\n"
                        f"Difficulty level: {difficulty}\n\n"
                        f"Base the questions on this study content:\n{content_text[:3000]}\n\n"
                        "Respond with ONLY a JSON array, no other text. Example format:\n"
                        '[{"type": "multiple_choice", "text": "What is...?", '
                        '"options": ["A", "B", "C", "D"], "correct_answer": "B"}]'
                    ),
                }
            ],
        )

        questions_raw = _parse_json(message.content[0].text, [])
    except Exception as e:
        logger.error(f"Claude API error in generate_questions: {e}")
        questions_raw = []

    questions = []
    for q in questions_raw[:num_questions]:
        q["id"] = str(uuid.uuid4())
        q["difficulty"] = difficulty
        # Ensure type field exists
        if "type" not in q:
            q["type"] = "multiple_choice" if "options" in q else "fill_blank"
        questions.append(q)

    return questions


def grade_answer(question: Dict[str, Any], user_answer: str) -> bool:
    """Grade a user's answer by simple comparison (case-insensitive for text)."""
    correct = question.get("correct_answer", "").strip().lower()
    user = user_answer.strip().lower()
    return user == correct


async def generate_study_guide(
    wrong_answers: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Generate study guide entries for a list of wrong answers."""
    study_guide = []
    for answer in wrong_answers:
        entry = await generate_study_guide_entry(
            answer.get("question_text", ""),
            answer.get("user_answer", ""),
            answer.get("correct_answer", ""),
        )
        study_guide.append(
            {
                "question_id": answer.get("question_id"),
                "topic": answer.get("topic", "General"),
                "explanation": entry["explanation"],
                "resource_link": "https://example.com/study",
                "difficulty_adjustment": entry.get("tips", "Review this topic"),
            }
        )
    return study_guide


async def generate_flashcards(
    content_text: str, num_cards: int, additional_prompts: str = None
) -> List[Dict[str, str]]:
    """Use Claude to generate flashcard pairs from study content."""
    client = get_client()

    extra = (
        f"\nAdditional instructions: {additional_prompts}" if additional_prompts else ""
    )

    try:
        message = await client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Create exactly {num_cards} flash cards based on this study material:\n\n"
                        f"{content_text[:3000]}{extra}\n\n"
                        'Respond with ONLY a JSON array. Each object must have "front" '
                        '(a question or term) and "back" (the answer or definition).\n'
                        'Example: [{"front": "What is X?", "back": "X is..."}]'
                    ),
                }
            ],
        )

        cards = _parse_json(message.content[0].text, [])
    except Exception as e:
        logger.error(f"Claude API error in generate_flashcards: {e}")
        cards = [
            {
                "front": "AI generation error",
                "back": "Could not generate flash cards. Please try again.",
            }
        ]

    return cards[:num_cards]


async def generate_study_guide_entry(
    question: str, user_answer: str, correct_answer: str
) -> Dict[str, str]:
    """Use Claude to generate an explanation and tips for a wrong answer."""
    client = get_client()

    try:
        message = await client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "A student answered this question incorrectly:\n\n"
                        f"Question: {question}\n"
                        f"Student's answer: {user_answer}\n"
                        f"Correct answer: {correct_answer}\n\n"
                        "Respond with ONLY a JSON object:\n"
                        '{"explanation": "<clear explanation of why the correct answer is right>'
                        '", "tips": "<specific study advice for this topic>'
                        '", "practice_question": "<a similar practice question>"}'
                    ),
                }
            ],
        )

        result = _parse_json(
            message.content[0].text,
            {
                "explanation": message.content[0].text[:300],
                "tips": "Review the material related to this topic and try similar practice problems.",
                "practice_question": "Can you explain this concept in your own words?",
            },
        )
    except Exception as e:
        logger.error(f"Claude API error in generate_study_guide_entry: {e}")
        result = {
            "explanation": "Review the correct answer and compare it with your response.",
            "tips": "Review the material and try again.",
            "practice_question": "Can you explain this concept in your own words?",
        }

    return result


async def generate_tutor_response(
    messages: List[Dict[str, str]], latest_message: str
) -> str:
    """Use Claude as an AI tutor to respond to student questions."""
    client = get_client()

    # Build conversation history for Claude (last 10 messages for context)
    claude_messages = []
    for msg in messages[-10:]:
        role = "user" if msg.get("role") == "user" else "assistant"
        content = msg.get("content", "")
        if content:
            claude_messages.append({"role": role, "content": content})

    # Ensure messages start with user and alternate properly
    if not claude_messages:
        claude_messages = [{"role": "user", "content": latest_message}]
    else:
        # Fix any consecutive same-role messages
        fixed = []
        for msg in claude_messages:
            if fixed and fixed[-1]["role"] == msg["role"]:
                fixed[-1]["content"] += "\n" + msg["content"]
            else:
                fixed.append(msg)
        claude_messages = fixed

        # Ensure first message is from user
        if claude_messages[0]["role"] != "user":
            claude_messages.insert(0, {"role": "user", "content": "Hello"})

        # Ensure last message is from user
        if claude_messages[-1]["role"] != "user":
            claude_messages.append({"role": "user", "content": latest_message})

    try:
        message = await client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=(
                "You are Quiz Wiz AI Tutor, a friendly, patient, and encouraging tutor "
                "for students of all ages. Help them understand concepts, solve problems, "
                "and learn effectively. Use simple explanations, helpful analogies, and "
                "guiding questions. Keep responses concise (2-4 paragraphs max) but "
                "thorough. If a student is struggling, break things down into smaller "
                "steps. Celebrate when they get things right!"
            ),
            messages=claude_messages,
        )

        return message.content[0].text
    except Exception as e:
        logger.error(f"Claude API error in generate_tutor_response: {e}")
        return (
            "I'm having a little trouble connecting right now. "
            "Could you try asking your question again in a moment?"
        )
