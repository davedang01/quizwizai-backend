import uuid
import json
import logging
import base64
import re
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Any

import anthropic

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from ..config import get_settings

logger = logging.getLogger(__name__)

if not HAS_PIL:
    logger.warning("[ai_stub] Pillow NOT installed — image compression disabled. Large images may fail.")

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


# ---------------------------------------------------------------------------
# 1. PDF / Text Analysis
# ---------------------------------------------------------------------------

async def analyze_content(text_or_base64: str) -> Dict[str, Any]:
    """Use Claude to analyze uploaded text/PDF content and extract metadata."""
    client = get_client()
    content_preview = text_or_base64[:8000]

    try:
        message = await client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system="You are an expert educational content analyzer. Always respond with valid JSON only, no markdown or extra text.",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Analyze this extracted text from a study document and provide:\n"
                        "1. A clean, formatted version of the content (remove any formatting artifacts)\n"
                        "2. Subject (e.g., Math, Science, History, English)\n"
                        "3. List of 3-5 main topics covered\n"
                        "4. Difficulty level (Easy, Medium, Hard)\n\n"
                        f"Content:\n{content_preview}\n\n"
                        "You MUST respond with ONLY valid JSON:\n"
                        '{"content_text": "cleaned and formatted content",'
                        ' "subject": "subject name",'
                        ' "topics": ["topic1", "topic2"],'
                        ' "difficulty": "level"}'
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
            "content_text": "",
            "analysis_failed": True,
        }

    content_text = result.get("content_text", "")
    analysis_failed = result.get("analysis_failed", False)

    if not analysis_failed and content_text:
        garbage_markers = [
            "ai analysis is temporarily unavailable",
            "content uploaded successfully",
            "unable to process",
        ]
        if any(marker in content_text.lower() for marker in garbage_markers):
            analysis_failed = True
        elif len(content_text.strip()) < 20:
            analysis_failed = True

    return {
        "id": str(uuid.uuid4()),
        "content_text": content_text,
        "subject": result.get("subject", "General"),
        "topics": result.get("topics", ["General"]),
        "difficulty": result.get("difficulty", "Medium"),
        "num_pages": 1,
        "analysis_failed": analysis_failed,
        "created_at": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# 2. Image Analysis (Vision API)
# ---------------------------------------------------------------------------

def _process_image_for_api(image_base64: str) -> tuple:
    """Process an image to ensure it's within Claude API's 5 MB base64 limit.

    Returns (processed_base64, media_type).

    Key insight: Claude's limit is 5 MB on the **base64 string**, not raw bytes.
    Base64 inflates size by ~33%, so we target 3.5 MB raw bytes → ~4.7 MB base64,
    safely under the 5 MB ceiling.
    """
    MAX_B64_BYTES = 5 * 1024 * 1024        # Claude's hard limit
    TARGET_RAW_BYTES = 3_500_000            # ~4.67 MB after base64 encoding

    # Strip data URL prefix if present (e.g., "data:image/heic;base64,")
    if image_base64.startswith("data:"):
        comma_index = image_base64.find(",")
        if comma_index != -1:
            image_base64 = image_base64[comma_index + 1:]

    # Detect media type from leading bytes
    if image_base64.startswith("iVBOR"):
        detected_media = "image/png"
    elif image_base64.startswith("R0lGOD"):
        detected_media = "image/gif"
    elif image_base64.startswith("UklGR"):
        detected_media = "image/webp"
    else:
        detected_media = "image/jpeg"

    # Quick check: if the base64 string is already under the limit, return as-is
    if len(image_base64) <= MAX_B64_BYTES:
        logger.info(f"[process_image] Image already under 5MB b64 limit (b64_len={len(image_base64)})")
        return image_base64, detected_media

    logger.info(f"[process_image] Image exceeds 5MB b64 limit (b64_len={len(image_base64)}), needs compression")

    if not HAS_PIL:
        logger.error("[process_image] Pillow NOT installed — cannot compress. Image will likely be rejected by API.")
        return image_base64, detected_media

    try:
        image_bytes = base64.b64decode(image_base64)
        img = Image.open(BytesIO(image_bytes))

        logger.info(
            f"[process_image] format={img.format} size={img.size} "
            f"mode={img.mode} raw_bytes={len(image_bytes)}"
        )

        # Convert mode if needed for JPEG output
        if img.mode == "P":
            img = img.convert("RGBA")
        elif img.mode not in ("RGB", "RGBA", "L"):
            img = img.convert("RGB")

        # Progressively resize until under target
        for scale in [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2]:
            if scale < 1.0:
                new_size = (int(img.width * scale), int(img.height * scale))
                resized = img.resize(new_size, Image.Resampling.LANCZOS)
            else:
                resized = img

            buf = BytesIO()
            # Flatten alpha channel for JPEG
            if resized.mode == "RGBA":
                bg = Image.new("RGB", resized.size, (255, 255, 255))
                bg.paste(resized, mask=resized.split()[3])
                bg.save(buf, format="JPEG", quality=85, optimize=True)
            else:
                if resized.mode != "RGB":
                    resized = resized.convert("RGB")
                resized.save(buf, format="JPEG", quality=85, optimize=True)

            compressed = buf.getvalue()
            compressed_b64 = base64.b64encode(compressed).decode("utf-8")

            if len(compressed_b64) <= MAX_B64_BYTES:
                logger.info(
                    f"[process_image] OK — scale={scale:.1f}, "
                    f"raw={len(compressed)} bytes, b64={len(compressed_b64)} bytes"
                )
                return compressed_b64, "image/jpeg"

            logger.info(f"[process_image] scale={scale:.1f} still too large: b64={len(compressed_b64)} bytes")

        # Last resort — very aggressive resize
        logger.warning("[process_image] All scales failed, using 0.15 scale")
        new_size = (int(img.width * 0.15), int(img.height * 0.15))
        resized = img.resize(new_size, Image.Resampling.LANCZOS)
        if resized.mode != "RGB":
            resized = resized.convert("RGB")
        buf = BytesIO()
        resized.save(buf, format="JPEG", quality=75, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8"), "image/jpeg"

    except Exception as e:
        logger.error(f"[process_image] Error: {type(e).__name__}: {e}")
        logger.error(f"[process_image] Returning original (b64_len={len(image_base64)}) — API may reject it")
        return image_base64, detected_media


async def analyze_images(images_base64: List[str]) -> Dict[str, Any]:
    """Use Claude Vision API to analyze uploaded images of study material."""
    client = get_client()
    num_pages = len(images_base64)

    # Build content blocks: images first, then the analysis prompt
    content_blocks: List[Dict[str, Any]] = []
    logger.info(f"[analyze_images] HAS_PIL={HAS_PIL}, num_images={num_pages}")

    for i, img_b64 in enumerate(images_base64[:10]):  # Limit to 10 images
        raw_len = len(img_b64)
        raw_bytes_approx = raw_len * 3 // 4  # base64 → bytes estimate
        logger.info(f"[analyze_images] Image {i+1}/{num_pages}: raw b64_len={raw_len} (~{raw_bytes_approx / 1024 / 1024:.1f}MB)")
        processed_b64, media_type = _process_image_for_api(img_b64)
        logger.info(f"[analyze_images] Image {i+1}/{num_pages}: after processing media_type={media_type}, b64_len={len(processed_b64)}")

        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": processed_b64,
            },
        })

    # Use appropriate prompt based on single vs multiple images
    if num_pages == 1:
        prompt_text = (
            "Analyze this homework/workbook image and provide:\n"
            "1. Full text content transcription — transcribe ALL text, numbers, equations, "
            "tables, graphs descriptions, and problems visible in the image. Be thorough.\n"
            "2. Subject (e.g., Math, Science, History, English)\n"
            "3. List of 3-5 main topics covered\n"
            "4. Difficulty level (Easy, Medium, Hard)\n\n"
            "IMPORTANT: The content_text field must contain a COMPLETE transcription of everything "
            "in the image, including all numbers, answer choices, table data, and problem text. "
            "Do NOT summarize — transcribe verbatim.\n\n"
            "You MUST respond with ONLY valid JSON, no other text:\n"
            '{"content_text": "complete transcribed text",'
            ' "subject": "subject name",'
            ' "topics": ["topic1", "topic2"],'
            ' "difficulty": "level"}'
        )
    else:
        prompt_text = (
            f"Analyze these {num_pages} pages of homework/workbook and provide:\n"
            "1. Full text content transcription from ALL pages — transcribe ALL text, numbers, "
            "equations, tables, graphs descriptions, and problems. Be thorough. Combine in page order.\n"
            "2. Subject (e.g., Math, Science, History, English)\n"
            f"3. List of 3-5 main topics covered across all {num_pages} pages\n"
            "4. Overall difficulty level (Easy, Medium, Hard)\n\n"
            "IMPORTANT: The content_text field must contain a COMPLETE transcription of everything "
            "across all pages, including all numbers, answer choices, table data, and problem text. "
            "Do NOT summarize — transcribe verbatim.\n\n"
            "You MUST respond with ONLY valid JSON, no other text:\n"
            '{"content_text": "combined transcribed text from all pages",'
            ' "subject": "subject name",'
            ' "topics": ["topic1", "topic2"],'
            ' "difficulty": "level"}'
        )

    content_blocks.append({"type": "text", "text": prompt_text})

    try:
        logger.info(f"[analyze_images] Sending {num_pages} image(s) to Claude Vision API")
        message = await client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system="You are an expert educational content analyzer. Always respond with valid JSON only, no markdown or extra text.",
            messages=[
                {
                    "role": "user",
                    "content": content_blocks,
                }
            ],
        )

        raw_text = message.content[0].text
        logger.info(f"[analyze_images] Claude response (first 300 chars): {raw_text[:300]}")
        result = _parse_json(
            raw_text,
            {
                "subject": "General",
                "topics": ["Study Material"],
                "difficulty": "Medium",
                "content_text": raw_text[:2000],
            },
        )
    except Exception as e:
        logger.error(f"[analyze_images] Claude API error: {type(e).__name__}: {e}")
        result = {
            "subject": "General",
            "topics": ["Study Material"],
            "difficulty": "Medium",
            "content_text": "",
            "analysis_failed": True,
        }

    content_text = result.get("content_text", "")
    analysis_failed = result.get("analysis_failed", False)

    # Detect garbage / placeholder content that would produce irrelevant questions
    if not analysis_failed and content_text:
        garbage_markers = [
            "ai analysis is temporarily unavailable",
            "content uploaded successfully",
            "unable to process",
        ]
        if any(marker in content_text.lower() for marker in garbage_markers):
            analysis_failed = True
        elif len(content_text.strip()) < 20:
            analysis_failed = True

    return {
        "id": str(uuid.uuid4()),
        "content_text": content_text,
        "subject": result.get("subject", "General"),
        "topics": result.get("topics", ["General"]),
        "difficulty": result.get("difficulty", "Medium"),
        "num_pages": num_pages,
        "analysis_failed": analysis_failed,
        "created_at": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# 3. Test Question Generation (per-type prompts)
# ---------------------------------------------------------------------------

# Difficulty instructions used across all question types
DIFFICULTY_INSTRUCTIONS = {
    "easy": "Create simple, straightforward questions suitable for beginners.",
    "medium": "Create moderate difficulty questions that require understanding of concepts.",
    "hard": "Create challenging questions that require deep understanding and critical thinking.",
}


def _build_mc_prompt(
    content_text: str, num_questions: int, difficulty: str,
    additional_prompts: str = None,
) -> str:
    """Build the multiple-choice question generation prompt."""
    diff_instruction = DIFFICULTY_INSTRUCTIONS.get(difficulty, DIFFICULTY_INSTRUCTIONS["medium"])
    extra = f"\n{additional_prompts}" if additional_prompts else ""

    return (
        f'Based on this content: "{content_text[:6000]}"\n\n'
        f"{diff_instruction}\n"
        f"Generate {num_questions} multiple-choice questions.\n"
        f"{extra}\n\n"
        "IMPORTANT RULES:\n"
        "- DO NOT copy questions exactly from the content - create NEW questions that test the SAME concepts\n"
        "- Questions should be SIMILAR in topic and difficulty but worded differently with different numbers/scenarios\n"
        "- Each question must have exactly 4 options\n"
        "- Only ONE option can be the correct answer\n"
        '- For approximately 20-30% of questions, include "None of the above" as one of the 4 options\n'
        '- When using "None of the above", ensure it is either correct (when all other options are wrong) '
        "or incorrect (when one other option is correct)\n"
        "- Make sure incorrect options are plausible but clearly wrong\n\n"
        "Respond with ONLY a JSON array, no other text:\n"
        '[{"id": "q1", "type": "multiple_choice", "text": "question text", '
        '"options": ["option A", "option B", "option C", "option D"], '
        '"correct_answer": "exact text of the ONE correct option"}]'
    )


def _build_word_problems_prompt(
    content_text: str, num_questions: int, difficulty: str,
    additional_prompts: str = None,
) -> str:
    """Build the word problems question generation prompt."""
    diff_instruction = DIFFICULTY_INSTRUCTIONS.get(difficulty, DIFFICULTY_INSTRUCTIONS["medium"])
    extra = f"\n{additional_prompts}" if additional_prompts else ""

    return (
        f'Based on this content: "{content_text[:6000]}"\n\n'
        f"{diff_instruction}\n"
        f"Generate {num_questions} word problems that require written answers.\n"
        f"{extra}\n\n"
        "IMPORTANT RULES:\n"
        "- DO NOT copy questions exactly from the content - create NEW questions that test the SAME concepts\n"
        "- Questions should be SIMILAR in topic and difficulty but use different scenarios, names, and numbers\n"
        "- The correct_answer should be ONLY the final answer (a number, fraction, or short phrase), NOT the steps\n"
        "- VERIFY your arithmetic: Double-check all calculations before providing the correct_answer\n"
        "- ALWAYS include the $ sign for dollar/money amounts in both the question text AND correct_answer\n\n"
        "Respond with ONLY a JSON array, no other text:\n"
        '[{"id": "q1", "type": "word_problem", "text": "detailed word problem", '
        '"correct_answer": "final answer only (e.g., \'3/8\' or \'42\' or \'$15.50\')"}]'
    )


def _build_math_prompt(
    content_text: str, num_questions: int, difficulty: str,
    additional_prompts: str = None,
) -> str:
    """Build the math problems question generation prompt."""
    diff_instruction = DIFFICULTY_INSTRUCTIONS.get(difficulty, DIFFICULTY_INSTRUCTIONS["medium"])
    extra = f"\n{additional_prompts}" if additional_prompts else ""

    return (
        f'Based on this mathematical content: "{content_text[:6000]}"\n\n'
        f"{diff_instruction}\n"
        f"Generate {num_questions} math problems.\n"
        f"{extra}\n\n"
        "CRITICAL REQUIREMENTS:\n"
        "- DO NOT copy problems exactly from the content - create NEW problems that test the SAME concepts\n"
        "- Problems should be SIMILAR in type and difficulty but use DIFFERENT numbers and scenarios\n"
        "- Focus on mathematical calculations, equations, and problem-solving\n"
        "- Cover various math concepts from the content (fractions, algebra, geometry, arithmetic, etc.)\n"
        '- The correct_answer MUST be ONLY the final numerical answer (e.g., "3/8", "42", "1 5/12", "2.5")\n'
        "- DO NOT include steps or explanations in correct_answer - ONLY the final answer\n"
        "- IMPORTANT: VERIFY YOUR ARITHMETIC! Double-check every calculation. For fractions:\n"
        "  * To convert improper fraction to mixed number: divide numerator by denominator\n"
        "  * Example: 29/10 = 2 remainder 9 = 2 9/10 (NOT 2 12/25)\n"
        "  * Always simplify fractions to lowest terms\n"
        "- ALWAYS include the $ sign for dollar/money amounts in both the question text AND correct_answer\n\n"
        "Respond with ONLY a JSON array, no other text:\n"
        '[{"id": "q1", "type": "math", "text": "detailed math problem", '
        '"correct_answer": "final answer only (e.g., \'3/8\' or \'1 5/12\' or \'$272\')"}]'
    )


def _build_fill_blank_prompt(
    content_text: str, num_questions: int, difficulty: str,
    additional_prompts: str = None,
) -> str:
    """Build the fill-in-the-blank question generation prompt."""
    diff_instruction = DIFFICULTY_INSTRUCTIONS.get(difficulty, DIFFICULTY_INSTRUCTIONS["medium"])
    extra = f"\n{additional_prompts}" if additional_prompts else ""

    return (
        f'Based on this content: "{content_text[:6000]}"\n\n'
        f"{diff_instruction}\n"
        f"Generate {num_questions} fill-in-the-blank questions.\n"
        f"{extra}\n\n"
        "IMPORTANT RULES:\n"
        "- DO NOT copy sentences exactly from the content - create NEW sentences that test the SAME concepts\n"
        "- Questions should test vocabulary, key terms, concepts, and understanding\n"
        "- Each question should be a sentence with ONE blank (indicated by _____)\n"
        "- The blank should replace a KEY word or phrase that tests understanding\n"
        "- The correct_answer should be ONLY the missing word or phrase (not the full sentence)\n"
        "- Make sure the blank is meaningful and tests important concepts, not trivial words\n\n"
        "Respond with ONLY a JSON array, no other text:\n"
        '[{"id": "q1", "type": "fill_blank", '
        '"text": "The _____ is the process by which plants convert sunlight into energy.", '
        '"correct_answer": "photosynthesis"}]'
    )


def _build_mixed_prompt(
    content_text: str, num_questions: int, difficulty: str,
    additional_prompts: str = None,
) -> str:
    """Build the mixed question type generation prompt."""
    diff_instruction = DIFFICULTY_INSTRUCTIONS.get(difficulty, DIFFICULTY_INSTRUCTIONS["medium"])
    extra = f"\n{additional_prompts}" if additional_prompts else ""

    return (
        f'Based on this content: "{content_text[:6000]}"\n\n'
        f"{diff_instruction}\n"
        f"Generate {num_questions} mixed questions (combination of multiple-choice, word problems, and fill-in-the-blank).\n"
        f"{extra}\n\n"
        "IMPORTANT RULES:\n"
        "- DO NOT copy questions exactly from the content - create NEW questions that test the SAME concepts\n"
        "- Questions should be SIMILAR in topic and difficulty but worded differently with different numbers/scenarios\n"
        "- Include a good mix of all three question types\n\n"
        "FOR MULTIPLE-CHOICE QUESTIONS:\n"
        "- Each multiple-choice question must have exactly 4 options\n"
        "- Only ONE option can be the correct answer\n"
        '- For approximately 20-30% of multiple-choice questions, include "None of the above" as one of the 4 options\n\n'
        "FOR WORD PROBLEMS:\n"
        "- The correct_answer should be ONLY the final answer, NOT the steps\n\n"
        "FOR FILL-IN-THE-BLANK QUESTIONS:\n"
        "- The question should have ONE blank (indicated by _____) where a key word or phrase should go\n"
        "- The correct_answer should be ONLY the missing word or phrase\n\n"
        "Respond with ONLY a JSON array, no other text:\n"
        '[{"id": "q1", "type": "multiple_choice", "text": "question text", '
        '"options": ["A", "B", "C", "D"], "correct_answer": "correct option text"}, '
        '{"id": "q2", "type": "word_problem", "text": "word problem text", '
        '"correct_answer": "final answer"}, '
        '{"id": "q3", "type": "fill_blank", "text": "The _____ is...", '
        '"correct_answer": "missing word"}]'
    )


# Map frontend test_type values to prompt builders
_PROMPT_BUILDERS = {
    "multiple-choice": _build_mc_prompt,
    "word-problems": _build_word_problems_prompt,
    "math-problems": _build_math_prompt,
    "fill-in-the-blank": _build_fill_blank_prompt,
    "mixed": _build_mixed_prompt,
}


async def generate_questions(
    content_text: str,
    test_type: str,
    difficulty: str,
    num_questions: int,
    topics: List[str] = None,
    additional_prompts: str = None,
) -> List[Dict[str, Any]]:
    """Use Claude to generate test questions based on content."""
    client = get_client()

    # Build additional context
    extra_parts = []
    if topics:
        extra_parts.append(f"Focus on these topics: {', '.join(topics)}")
    if additional_prompts:
        extra_parts.append(additional_prompts)
    extra = "\n".join(extra_parts) if extra_parts else None

    # Select the right prompt builder (default to mixed)
    builder = _PROMPT_BUILDERS.get(test_type, _build_mixed_prompt)
    prompt = builder(content_text, num_questions, difficulty, extra)

    system_msg = f"You are an expert test creator. Generate {difficulty} level educational questions."

    try:
        logger.info(f"[generate_questions] type={test_type}, model={MODEL}, num={num_questions}, content_len={len(content_text)}")
        message = await client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system_msg,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = message.content[0].text
        logger.info(f"[generate_questions] Claude response (first 300 chars): {raw_text[:300]}")

        # Parse — Emergent wraps in {"questions": [...]}, we also handle bare arrays
        parsed = _parse_json(raw_text, [])
        if isinstance(parsed, dict) and "questions" in parsed:
            questions_raw = parsed["questions"]
        elif isinstance(parsed, list):
            questions_raw = parsed
        else:
            questions_raw = []

        logger.info(f"[generate_questions] Parsed {len(questions_raw)} questions")
    except Exception as e:
        logger.error(f"[generate_questions] Claude API error: {type(e).__name__}: {e}")
        questions_raw = []

    questions = []
    for q in questions_raw[:num_questions]:
        q["id"] = str(uuid.uuid4())
        q["difficulty"] = difficulty
        # Normalise type field — map Emergent-style types to our internal types
        qtype = q.get("type", "")
        if "multiple" in qtype.lower() or "options" in q:
            q["type"] = "multiple_choice"
        elif "word" in qtype.lower():
            q["type"] = "word_problem"
        elif "math" in qtype.lower():
            q["type"] = "math"
        elif "fill" in qtype.lower() or "blank" in qtype.lower():
            q["type"] = "fill_blank"
        elif "type" not in q:
            q["type"] = "multiple_choice" if "options" in q else "fill_blank"
        # Normalise question field — Emergent uses "question", our frontend uses "text"
        if "question" in q and "text" not in q:
            q["text"] = q.pop("question")
        questions.append(q)

    logger.info(f"[generate_questions] Returning {len(questions)} questions")
    return questions


# ---------------------------------------------------------------------------
# 4. Answer Grading
# ---------------------------------------------------------------------------

def _normalize_answer(answer: str) -> str:
    """Normalize answer for comparison — strip whitespace, currency, commas."""
    if not answer:
        return ""
    normalized = " ".join(answer.strip().lower().split())
    normalized = normalized.replace("$", "").replace(",", "")
    return normalized


def _parse_number(s: str) -> float:
    """Parse a number string including fractions and mixed numbers."""
    s = s.strip()
    if " " in s and "/" in s:
        parts = s.split(" ", 1)
        whole = float(parts[0])
        frac_parts = parts[1].split("/")
        return whole + float(frac_parts[0]) / float(frac_parts[1])
    if "/" in s:
        parts = s.split("/")
        return float(parts[0]) / float(parts[1])
    return float(s)


def _answers_equivalent(user_ans: str, correct_ans: str) -> bool:
    """Check if two answers are equivalent — handles fractions, decimals, mixed numbers."""
    user_norm = _normalize_answer(user_ans)
    correct_norm = _normalize_answer(correct_ans)
    if user_norm == correct_norm:
        return True
    try:
        user_val = _parse_number(user_norm)
        correct_val = _parse_number(correct_norm)
        if abs(user_val - correct_val) < 0.01:
            return True
    except (ValueError, ZeroDivisionError, IndexError):
        pass
    return False


def grade_answer(question: Dict[str, Any], user_answer: str) -> bool:
    """Grade using normalize + numeric equivalence (Tier 1+2)."""
    return _answers_equivalent(user_answer, question.get("correct_answer", ""))


async def grade_answer_smart(question: Dict[str, Any], user_answer: str) -> Dict[str, Any]:
    """3-tier grading: normalize → numeric equivalence → LLM verification."""
    correct = question.get("correct_answer", "").strip()
    user = user_answer.strip()

    # Tier 1+2: Normalize and check equivalence
    if _answers_equivalent(user, correct):
        return {"is_correct": True, "explanation": "", "correct_answer": correct}

    # Tier 3: LLM verification
    client = get_client()
    try:
        message = await client.messages.create(
            model=MODEL,
            max_tokens=512,
            system="You are a math teacher verifying student answers. Be accurate with arithmetic.",
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Verify if this student's answer is mathematically correct for the given problem.\n\n"
                        f"PROBLEM: {question.get('text', '')}\n\n"
                        f"STUDENT'S ANSWER: {user}\n\n"
                        "Solve the problem step by step, then determine if the student's answer is correct.\n"
                        "Consider equivalent forms (e.g., 2 9/10 = 29/10 = 2.9).\n\n"
                        'Respond with ONLY valid JSON:\n'
                        '{"is_correct": true or false, "actual_answer": "the correct answer"}'
                    ),
                }
            ],
        )
        result = _parse_json(
            message.content[0].text,
            {"is_correct": False, "actual_answer": correct},
        )
        return {
            "is_correct": result.get("is_correct", False),
            "explanation": "",
            "correct_answer": result.get("actual_answer", correct),
        }
    except Exception as e:
        logger.error(f"Claude API error in grade_answer_smart: {e}")
        return {"is_correct": False, "explanation": "", "correct_answer": correct}


async def check_math_content(content_text: str) -> bool:
    """Check if content is math-related. Used to validate 'Math Problems' test type.

    Uses a generous keyword check. If ANY numbers or math-adjacent terms are found,
    we allow it. The purpose is only to block clearly non-math content (e.g., a
    pure literature passage with zero numbers).
    """
    import re

    text_lower = content_text.lower()
    logger.info(f"[check_math_content] Content length: {len(content_text)}, first 200 chars: {content_text[:200]}")

    # Check 1: Does the content contain ANY numbers? Math content always has numbers.
    has_any_numbers = bool(re.search(r'\d', content_text))
    if has_any_numbers:
        logger.info("[check_math_content] PASS — content contains numbers")
        return True

    # Check 2: Math-related keywords (fallback for edge cases)
    math_keywords = [
        "math", "equation", "solve", "calculate", "multiply", "divide", "subtract", "add",
        "fraction", "decimal", "percent", "graph", "coordinate", "axis",
        "algebra", "geometry", "arithmetic", "number",
        "sum", "difference", "product", "quotient", "area", "perimeter", "volume",
        "angle", "ratio", "proportion", "variable", "expression",
        "table", "chart", "plot", "ordered pair", "function", "slope",
    ]
    has_keyword = any(kw in text_lower for kw in math_keywords)
    if has_keyword:
        logger.info("[check_math_content] PASS — content contains math keyword")
        return True

    logger.info("[check_math_content] FAIL — no numbers or math keywords found")
    return False


# ---------------------------------------------------------------------------
# 5. Study Guide Generation
# ---------------------------------------------------------------------------

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


async def generate_study_guide_entry(
    question: str, user_answer: str, correct_answer: str
) -> Dict[str, str]:
    """Use Claude to generate an explanation and tips for a wrong answer."""
    client = get_client()

    try:
        message = await client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=(
                "You are a friendly, encouraging tutor helping students aged 10-16. "
                "Look at the question content to gauge the student's likely grade level "
                "(e.g., basic multiplication = younger ~10-11, algebra = ~13-14, geometry proofs = ~15-16). "
                "Tailor your language and explanations to match their age — use simple words for younger "
                "students, more detailed reasoning for older ones. "
                "Be warm and encouraging. Use relatable examples. "
                "NEVER use LaTeX — write fractions as 3/4, not \\frac{3}{4}."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Question: {question}\n"
                        f"Student's Answer: {user_answer}\n"
                        f"Correct Answer: {correct_answer}\n\n"
                        "Provide:\n"
                        "1. A brief, age-appropriate explanation of why the correct answer is right "
                        "(use a relatable analogy or everyday example if it helps)\n"
                        "2. A memorable tip or trick to remember this concept\n"
                        "3. A similar practice question for the student to try\n\n"
                        "Respond in JSON format:\n"
                        '{"explanation": "explanation text",'
                        ' "tips": "helpful tips",'
                        ' "practice_question": "similar question for practice"}'
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


# ---------------------------------------------------------------------------
# 6. Flashcard Generation
# ---------------------------------------------------------------------------

async def generate_flashcards(
    content_text: str,
    num_cards: int,
    additional_prompts: str = None,
    topics: List[str] = None,
) -> List[Dict[str, str]]:
    """Use Claude to generate flashcard pairs from study content."""
    client = get_client()

    topics_note = f"\nFocus on these topics: {', '.join(topics)}" if topics else ""
    extra = (
        f"\n{additional_prompts}" if additional_prompts else ""
    )

    try:
        message = await client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system="You are an expert flashcard creator. Create effective study cards.",
            messages=[
                {
                    "role": "user",
                    "content": (
                        f'Based on this content: "{content_text[:4000]}"\n\n'
                        f"Generate {num_cards} flash cards for studying.\n"
                        f"{topics_note}{extra}\n\n"
                        "REQUIREMENTS:\n"
                        "- Each card should have a front (question/term) and back (answer/definition)\n"
                        "- Focus on key concepts, definitions, formulas, and important facts\n"
                        "- Make questions clear and answers concise\n"
                        "- Cover the main topics from the content\n"
                        "- Vary question types: definitions, explanations, applications, examples\n\n"
                        "Respond with ONLY a JSON array, no other text:\n"
                        '[{"front": "Question or term", "back": "Answer or definition"}]'
                    ),
                }
            ],
        )

        parsed = _parse_json(message.content[0].text, [])
        # Handle {"cards": [...]} wrapper
        if isinstance(parsed, dict) and "cards" in parsed:
            cards = parsed["cards"]
        elif isinstance(parsed, list):
            cards = parsed
        else:
            cards = []
    except Exception as e:
        logger.error(f"Claude API error in generate_flashcards: {e}")
        cards = [
            {
                "front": "AI generation error",
                "back": "Could not generate flash cards. Please try again.",
            }
        ]

    return cards[:num_cards]


# ---------------------------------------------------------------------------
# 7. AI Tutor / Homework Assistant
# ---------------------------------------------------------------------------

TUTOR_SYSTEM_PROMPT = (
    "You are Quiz Wiz AI's Homework Assistant - a helpful, friendly, and educational AI tutor "
    "designed for students aged 10-16 (roughly grades 5-10).\n\n"
    "AUDIENCE & TONE:\n"
    "- Your students are between 10 and 16 years old\n"
    "- Use language that matches their level — clear, simple words; short sentences\n"
    "- Be warm, encouraging, and patient like a favorite teacher or older sibling\n"
    "- Use relatable examples (sports, games, everyday life) to explain concepts\n"
    "- Celebrate effort and progress, not just correct answers\n"
    "- When explaining something hard, break it into small bite-sized steps\n"
    "- Use phrases like 'Great question!', 'You're on the right track!', 'Let's figure this out together!'\n\n"
    "Your primary role is to:\n"
    "1. Help students understand academic concepts\n"
    "2. Guide them through homework problems without simply giving answers\n"
    "3. Explain topics in clear, easy-to-understand language appropriate for their age\n"
    "4. Encourage learning and critical thinking\n"
    "5. Provide hints and perspectives to help students solve problems themselves\n\n"
    "IMPORTANT RULES:\n"
    "- You are ONLY for academic/educational topics (math, science, history, language arts, etc.)\n"
    "- If a user asks about non-academic topics (personal advice, entertainment, general chat, etc.), "
    "politely redirect them\n"
    "- Never simply provide answers to homework - guide the student to find the answer themselves\n"
    "- Use encouraging language and celebrate when students understand concepts\n"
    "- If you see an image or file, analyze it and help explain the content\n"
    "- Keep responses concise — students this age lose focus with long walls of text\n\n"
    "MATH FORMATTING RULES (VERY IMPORTANT):\n"
    "- NEVER use LaTeX notation like \\frac{1}{2} or $\\frac{a}{b}$\n"
    "- Always write fractions using a forward slash, like 1/2, 3/4, 7/8\n"
    "- For mixed numbers, write them as: 1 1/2 (one and one-half) or 2 3/4 (two and three-quarters)\n"
    "- Use plain text for all math: x^2 for squares, sqrt() for square roots, * for multiplication\n"
    "- ALWAYS include the $ sign for dollar amounts: $272, $15.50, $3.99 (never just 272)\n"
    "- Examples of correct formatting:\n"
    "  - Fraction: 3/4 (not \\frac{3}{4})\n"
    "  - Mixed number: 2 1/2 (not 2\\frac{1}{2})\n"
    "  - Division: 10 / 2 or 10/2 (not \\div)\n"
    "  - Money: $272 (not 272 or $\\$272$)\n\n"
    'When responding to non-academic queries, say: "I appreciate your trust in me, but I\'m just a '
    'homework assistant. Please ask me any questions that are study-related!"\n\n'
    "Be concise but thorough. Use examples when helpful. Format responses with markdown for clarity."
)


async def generate_tutor_response(
    messages: List[Dict[str, str]],
    latest_message: str,
    image_base64: str = None,
) -> str:
    """Use Claude as an AI tutor to respond to student questions.

    If image_base64 is provided, the image is sent directly to Claude Vision
    alongside the text so Claude can actually *see* the student's homework.
    """
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

    # If an image is attached, replace the last user message with a multimodal
    # content block so Claude can see the image directly.
    if image_base64:
        processed_b64, media_type = _process_image_for_api(image_base64)
        text_content = latest_message or "Can you help me with this?"

        multimodal_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": processed_b64,
                },
            },
            {"type": "text", "text": text_content},
        ]

        # Replace or append the last user message with the multimodal version
        if claude_messages and claude_messages[-1]["role"] == "user":
            claude_messages[-1]["content"] = multimodal_content
        else:
            claude_messages.append({"role": "user", "content": multimodal_content})

    try:
        message = await client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=TUTOR_SYSTEM_PROMPT,
            messages=claude_messages,
        )

        return message.content[0].text
    except Exception as e:
        logger.error(f"Claude API error in generate_tutor_response: {e}")
        return (
            "I'm having a little trouble connecting right now. "
            "Could you try asking your question again in a moment?"
        )
