import uuid
import json
import logging
import base64
import asyncio
import os
import re
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Any, Optional

import httpx

from ..config import get_settings

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger(__name__)
_settings = get_settings()

if not HAS_PIL:
    logger.warning("[ai_stub] Pillow NOT installed — image compression disabled. Large images may fail.")

# Model split:
# - VISION_MODEL handles scanned images (Opus 4.7 — first Claude model with
#   high-resolution image support, up to 2576px / 3.75MP). Used for OCR/vision
#   on student homework, worksheets, textbook pages.
# - TEXT_MODEL handles all text-only generation (quiz questions, flashcards,
#   tutor responses without images, grading, study guides). Sonnet 4.6 is fast,
#   cheap, and plenty capable for these.
VISION_MODEL = "claude-opus-4-7"
TEXT_MODEL = "claude-sonnet-4-6"

# Ensure the claude CLI binary is on PATH regardless of how pm2 launched us
_CLAUDE_PATH_ENV = {
    **os.environ,
    "PATH": f"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{os.environ.get('PATH', '')}",
}


async def _call_claude_cli(
    messages: List[Dict[str, Any]],
    system_prompt: str,
    model: str,
) -> str:
    """Invoke claude --print as a subprocess using the local Claude Code CLI.

    Supports single-turn text calls (simple stdin piping) and multi-turn or
    multimodal calls (stream-json format including base64 image content blocks).
    Auth is handled automatically by the Claude Code CLI via the user's local
    session — no API key required.
    """
    # Use stream-json when there are multiple messages or any message has
    # non-string content (i.e., a list of content blocks including images).
    needs_stream = len(messages) > 1 or any(
        not isinstance(m.get("content"), str) for m in messages
    )

    base_cmd = [
        "claude", "--print",
        "--model", model,
        "--system-prompt", system_prompt,
        "--no-session-persistence",
        "--tools", "",
    ]

    if needs_stream:
        # stream-json input requires stream-json output (CLI enforces this)
        cmd = base_cmd + [
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
        ]
        lines = []
        for m in messages:
            content = m["content"]
            # stream-json requires content as an array of blocks, not a bare string
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            lines.append(
                json.dumps({"type": m["role"], "message": {"role": m["role"], "content": content}}) + "\n"
            )
        stdin_data = "".join(lines).encode()
    else:
        cmd = base_cmd + ["--output-format", "text", "--input-format", "text"]
        stdin_data = (messages[0]["content"] if messages else "").encode()

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_CLAUDE_PATH_ENV,
    )
    stdout, stderr = await proc.communicate(input=stdin_data)
    raw = stdout.decode()

    if needs_stream:
        # Parse stream-json output: find the assistant message text block
        for line in raw.splitlines():
            try:
                ev = json.loads(line)
                if ev.get("type") == "result" and ev.get("is_error"):
                    err_msg = ev.get("result", "unknown error")
                    logger.error("[claude_cli] API error in stream-json result: %s", err_msg)
                    raise RuntimeError(f"claude CLI stream error: {err_msg}")
                if ev.get("type") == "assistant":
                    for block in ev.get("message", {}).get("content", []):
                        if block.get("type") == "text":
                            return block["text"]
            except (json.JSONDecodeError, RuntimeError):
                raise
            except Exception:
                pass
        raise RuntimeError("claude CLI stream-json: no assistant text found in output")

    if proc.returncode != 0:
        err = stderr.decode()
        logger.error("[claude_cli] exit=%d stderr=%s", proc.returncode, err[:500])
        raise RuntimeError(f"claude CLI: {err}")
    return raw.strip()


def _anthropic_content_to_openai(content: Any) -> Any:
    """Convert Anthropic-style multimodal content blocks to OpenAI's format.

    Our message-building code (analyze_images, tutor-with-image) constructs
    Claude-style {"type": "image", "source": {...}} blocks. OpenRouter speaks
    the OpenAI format ({"type": "image_url", "image_url": {"url": "data:..."}})
    instead, so this is only needed on the OpenRouter path.
    """
    if isinstance(content, str):
        return content
    converted = []
    for block in content:
        if block.get("type") == "image":
            media_type = block["source"]["media_type"]
            data = block["source"]["data"]
            converted.append({
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{data}"},
            })
        else:
            converted.append(block)
    return converted


async def _call_openrouter(
    messages: List[Dict[str, Any]],
    system_prompt: str,
    model: str,
) -> str:
    """Invoke a model via OpenRouter's OpenAI-compatible chat completions API."""
    full_messages = [{"role": "system", "content": system_prompt}] + [
        {"role": m["role"], "content": _anthropic_content_to_openai(m["content"])}
        for m in messages
    ]

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {_settings.openrouter_api_key}"},
            json={"model": model, "messages": full_messages},
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


async def _call_text_model(
    messages: List[Dict[str, Any]],
    system_prompt: str,
) -> str:
    """Dispatch a text-only AI call per ai_text_provider (quiz/flashcard/study-guide/
    grading/tutor-without-image). Vision calls never go through here — see _call_vision_model.
    """
    if _settings.ai_text_provider == "openrouter":
        return await _call_openrouter(messages, system_prompt, model=_settings.openrouter_text_model)
    return await _call_claude_cli(messages, system_prompt, model=TEXT_MODEL)


async def _call_vision_model(
    messages: List[Dict[str, Any]],
    system_prompt: str,
) -> str:
    """Dispatch a vision AI call per ai_vision_provider (photo/PDF scanning, tutor-with-image)."""
    if _settings.ai_vision_provider == "openrouter":
        return await _call_openrouter(messages, system_prompt, model=_settings.openrouter_vision_model)
    return await _call_claude_cli(messages, system_prompt, model=VISION_MODEL)


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
    content_preview = text_or_base64[:8000]

    try:
        raw_text = await _call_text_model(
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
            system_prompt="You are an expert educational content analyzer. Always respond with valid JSON only, no markdown or extra text.",
        )

        result = _parse_json(
            raw_text,
            {
                "subject": "General",
                "topics": ["Study Material"],
                "difficulty": "Medium",
                "content_text": raw_text[:500],
            },
        )
    except Exception as e:
        logger.error(f"Claude CLI error in analyze_content: {e}")
        result = {
            "subject": "General",
            "topics": ["Study Material"],
            "difficulty": "Medium",
            "content_text": "",
            "analysis_failed": True,
        }

    content_text = result.get("content_text", "")
    analysis_failed = result.get("analysis_failed", False)

    if not content_text:
        analysis_failed = True

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
    """Use Claude Vision to analyze uploaded images of study material."""
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
            "You are looking at a PHOTO of a student's homework, worksheet, notes, or textbook page.\n\n"
            "Your job is to READ and TRANSCRIBE the educational CONTENT written or printed ON the paper/page "
            "visible in the photo.\n\n"
            "CRITICAL RULES — READ CAREFULLY:\n"
            "- DO NOT describe the photo itself (e.g., do NOT mention pixels, resolution, file size, "
            "JPEG, image dimensions, compression, or any properties of the photograph)\n"
            "- DO NOT analyze the camera, lighting, or image quality\n"
            "- ONLY transcribe the text, numbers, equations, problems, and educational content "
            "that is written or printed ON the physical page being photographed\n"
            "- If you see handwritten or printed study material, copy it verbatim\n\n"
            "Provide:\n"
            "1. Full verbatim transcription of ALL text on the page (homework problems, notes, "
            "vocabulary, equations, tables, answer choices, etc.)\n"
            "2. Subject (e.g., Math, Science, History, English, Computer Science)\n"
            "3. List of 3-5 main topics covered\n"
            "4. Difficulty level (Easy, Medium, Hard)\n\n"
            "You MUST respond with ONLY valid JSON, no other text:\n"
            '{"content_text": "complete verbatim transcription of the page content",'
            ' "subject": "subject name",'
            ' "topics": ["topic1", "topic2"],'
            ' "difficulty": "level"}'
        )
    else:
        prompt_text = (
            f"You are looking at {num_pages} PHOTOS of a student's homework, worksheet, notes, or textbook pages.\n\n"
            "Your job is to READ and TRANSCRIBE the educational CONTENT written or printed ON each page "
            "visible in the photos.\n\n"
            "CRITICAL RULES — READ CAREFULLY:\n"
            "- DO NOT describe the photos themselves (e.g., do NOT mention pixels, resolution, file size, "
            "JPEG, image dimensions, compression, or any properties of the photographs)\n"
            "- DO NOT analyze the camera, lighting, or image quality\n"
            "- ONLY transcribe the text, numbers, equations, problems, and educational content "
            "that is written or printed ON the physical pages being photographed\n"
            "- Combine content from all pages in order\n\n"
            "Provide:\n"
            f"1. Full verbatim transcription of ALL text across all {num_pages} pages (homework problems, "
            "notes, vocabulary, equations, tables, answer choices, etc.)\n"
            "2. Subject (e.g., Math, Science, History, English, Computer Science)\n"
            f"3. List of 3-5 main topics covered across all {num_pages} pages\n"
            "4. Overall difficulty level (Easy, Medium, Hard)\n\n"
            "You MUST respond with ONLY valid JSON, no other text:\n"
            '{"content_text": "combined verbatim transcription from all pages",'
            ' "subject": "subject name",'
            ' "topics": ["topic1", "topic2"],'
            ' "difficulty": "level"}'
        )

    content_blocks.append({"type": "text", "text": prompt_text})

    try:
        logger.info(f"[analyze_images] Sending {num_pages} image(s) to vision model ({_settings.ai_vision_provider})")
        raw_text = await _call_vision_model(
            messages=[{"role": "user", "content": content_blocks}],
            system_prompt=(
                "You are an expert educational content analyzer. Your task is to READ the text and "
                "educational content printed or written on physical pages shown in photos. "
                "You must NEVER describe the photo/image file itself (no mentions of pixels, resolution, "
                "JPEG format, file size, or image properties). "
                "Always respond with valid JSON only, no markdown or extra text."
            ),
        )

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
        logger.error(f"[analyze_images] Claude CLI error: {type(e).__name__}: {e}")
        result = {
            "subject": "General",
            "topics": ["Study Material"],
            "difficulty": "Medium",
            "content_text": "",
            "analysis_failed": True,
        }

    content_text = result.get("content_text", "")
    analysis_failed = result.get("analysis_failed", False)

    if not content_text:
        analysis_failed = True

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

    # Contextual metadata-hallucination detection: if Claude described image
    # file properties (JPEG, chroma subsampling, pixel resolution, etc.) instead
    # of transcribing the page, we get bad downstream questions. Only flag this
    # when the detected subject is NOT a CS/image-processing field — otherwise
    # we'd false-flag legit textbook scans about image processing.
    if not analysis_failed and content_text:
        subject_lower = (result.get("subject") or "").lower()
        topics_blob = " ".join(result.get("topics") or []).lower()
        cs_signals = [
            "computer", "programming", "software", "image processing",
            "digital signal", "encoding", "informatics", "data structure",
            "compression algorithm",
        ]
        is_cs_subject = any(s in subject_lower or s in topics_blob for s in cs_signals)

        metadata_terms = [
            "chroma subsampling", "4:2:0", "4:4:4", "4:2:2",
            "luminance sample", "chrominance sample",
            "8x8 block", "8×8 block", "macroblock",
            "jpeg compression", "compression ratio",
            "pixel resolution", "image resolution", "image dimensions",
            "exif metadata", "color depth",
        ]
        content_lower = content_text.lower()
        metadata_hits = sum(1 for term in metadata_terms if term in content_lower)

        if metadata_hits >= 2 and not is_cs_subject:
            logger.warning(
                f"[analyze_images] Suspected metadata hallucination "
                f"(hits={metadata_hits}, subject={subject_lower!r}) — flagging as failed"
            )
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
        f'CONTENT (the study material the student is learning):\n"""\n{content_text[:6000]}\n"""\n\n'
        f"{diff_instruction}\n"
        f"Generate {num_questions} multiple-choice questions based STRICTLY on the CONTENT above.\n"
        f"{extra}\n\n"
        "STRICT GROUNDING (read this first):\n"
        "- Every question MUST be about a topic, vocabulary term, or concept that ACTUALLY APPEARS\n"
        "  in the CONTENT. Do NOT introduce topics not present in the content.\n\n"
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
        f'CONTENT (the study material the student is learning):\n"""\n{content_text[:6000]}\n"""\n\n'
        f"{diff_instruction}\n"
        f"Generate {num_questions} word problems based STRICTLY on the CONTENT above.\n"
        f"{extra}\n\n"
        "STRICT GROUNDING (read this first):\n"
        "- Every question MUST be about a topic, vocabulary term, or concept that ACTUALLY APPEARS\n"
        "  in the CONTENT. Do NOT introduce topics not present in the content (e.g., do not invent\n"
        "  finance, retail, or unrelated math problems if they are not in the content).\n\n"
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
        f'CONTENT (the study material the student is learning):\n"""\n{content_text[:6000]}\n"""\n\n'
        f"{diff_instruction}\n"
        f"Generate {num_questions} math questions based STRICTLY on the CONTENT above.\n"
        f"{extra}\n\n"
        "STRICT GROUNDING (read this first — it overrides everything below):\n"
        "- Every question MUST be about a specific topic, vocabulary term, classification, formula,\n"
        "  or skill that ACTUALLY APPEARS in the CONTENT. If the content is about classifying\n"
        "  triangles, generate questions about classifying triangles — NOT about percentages,\n"
        "  compound interest, gardens, JPEG compression, or any topic not in the content.\n"
        "- DO NOT introduce math topics not present in the content. The student is studying THIS\n"
        "  specific material, not generic math.\n"
        "- If the content is conceptual (classifying shapes, identifying properties, naming\n"
        "  vocabulary), generate conceptual questions — answers can be words like \"scalene\" or\n"
        "  \"obtuse\", not just numbers. Do not force arithmetic onto non-arithmetic content.\n\n"
        "OTHER REQUIREMENTS:\n"
        "- DO NOT copy problems verbatim from the content — create NEW problems that test\n"
        "  the SAME specific concepts using fresh wording or examples.\n"
        '- The correct_answer MUST be ONLY the final answer (e.g., "3/8", "42", "1 5/12", "2.5",\n'
        '  "scalene", "obtuse") — no steps or explanations.\n'
        "- VERIFY arithmetic when calculations are involved. For fractions:\n"
        "  * To convert improper fraction to mixed number: divide numerator by denominator\n"
        "  * Example: 29/10 = 2 remainder 9 = 2 9/10 (NOT 2 12/25)\n"
        "  * Always simplify fractions to lowest terms\n"
        "- ALWAYS include the $ sign for dollar/money amounts in both question text AND correct_answer\n\n"
        "Respond with ONLY a JSON array, no other text:\n"
        '[{"id": "q1", "type": "math", "text": "detailed problem", '
        '"correct_answer": "final answer only"}]'
    )


def _build_fill_blank_prompt(
    content_text: str, num_questions: int, difficulty: str,
    additional_prompts: str = None,
) -> str:
    """Build the fill-in-the-blank question generation prompt."""
    diff_instruction = DIFFICULTY_INSTRUCTIONS.get(difficulty, DIFFICULTY_INSTRUCTIONS["medium"])
    extra = f"\n{additional_prompts}" if additional_prompts else ""

    return (
        f'CONTENT (the study material the student is learning):\n"""\n{content_text[:6000]}\n"""\n\n'
        f"{diff_instruction}\n"
        f"Generate {num_questions} fill-in-the-blank questions based STRICTLY on the CONTENT above.\n"
        f"{extra}\n\n"
        "STRICT GROUNDING (read this first):\n"
        "- Every question MUST test a vocabulary term, concept, or fact that ACTUALLY APPEARS in\n"
        "  the CONTENT. Do NOT introduce topics not present in the content.\n\n"
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
        f'CONTENT (the study material the student is learning):\n"""\n{content_text[:6000]}\n"""\n\n'
        f"{diff_instruction}\n"
        f"Generate {num_questions} mixed questions (combination of multiple-choice, word problems, and fill-in-the-blank) based STRICTLY on the CONTENT above.\n"
        f"{extra}\n\n"
        "STRICT GROUNDING (read this first):\n"
        "- Every question MUST be about a topic, vocabulary term, or concept that ACTUALLY APPEARS\n"
        "  in the CONTENT. Do NOT introduce topics not present in the content.\n\n"
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
        logger.info(f"[generate_questions] type={test_type}, provider={_settings.ai_text_provider}, num={num_questions}, content_len={len(content_text)}")
        raw_text = await _call_text_model(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=system_msg,
        )

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
        logger.error(f"[generate_questions] Claude CLI error: {type(e).__name__}: {e}")
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
    try:
        raw_text = await _call_text_model(
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
            system_prompt="You are a math teacher verifying student answers. Be accurate with arithmetic.",
        )
        result = _parse_json(
            raw_text,
            {"is_correct": False, "actual_answer": correct},
        )
        return {
            "is_correct": result.get("is_correct", False),
            "explanation": "",
            "correct_answer": result.get("actual_answer", correct),
        }
    except Exception as e:
        logger.error(f"Claude CLI error in grade_answer_smart: {e}")
        return {"is_correct": False, "explanation": "", "correct_answer": correct}


async def check_math_content(content_text: str) -> bool:
    """Check if content is math-related. Used to validate 'Math Problems' test type.

    Uses a generous keyword check. If ANY numbers or math-adjacent terms are found,
    we allow it. The purpose is only to block clearly non-math content (e.g., a
    pure literature passage with zero numbers).
    """
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
    try:
        raw_text = await _call_text_model(
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
            system_prompt=(
                "You are a friendly, encouraging tutor helping students aged 10-16. "
                "Look at the question content to gauge the student's likely grade level "
                "(e.g., basic multiplication = younger ~10-11, algebra = ~13-14, geometry proofs = ~15-16). "
                "Tailor your language and explanations to match their age — use simple words for younger "
                "students, more detailed reasoning for older ones. "
                "Be warm and encouraging. Use relatable examples. "
                "NEVER use LaTeX — write fractions as 3/4, not \\frac{3}{4}."
            ),
        )

        result = _parse_json(
            raw_text,
            {
                "explanation": raw_text[:300],
                "tips": "Review the material related to this topic and try similar practice problems.",
                "practice_question": "Can you explain this concept in your own words?",
            },
        )
    except Exception as e:
        logger.error(f"Claude CLI error in generate_study_guide_entry: {e}")
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
    topics_note = f"\nFocus on these topics: {', '.join(topics)}" if topics else ""
    extra = f"\n{additional_prompts}" if additional_prompts else ""

    try:
        raw_text = await _call_text_model(
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
            system_prompt="You are an expert flashcard creator. Create effective study cards.",
        )

        parsed = _parse_json(raw_text, [])
        # Handle {"cards": [...]} wrapper
        if isinstance(parsed, dict) and "cards" in parsed:
            cards = parsed["cards"]
        elif isinstance(parsed, list):
            cards = parsed
        else:
            cards = []
    except Exception as e:
        logger.error(f"Claude CLI error in generate_flashcards: {e}")
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


async def generate_session_title(user_message: str, assistant_response: str) -> str:
    """Generate a short descriptive title for a tutor chat session after the first exchange."""
    try:
        prompt = (
            f"Write a short 4-6 word title for this tutoring conversation. "
            f"No quotes, no period, just the title.\n\n"
            f"Student: {user_message[:300]}\n\nTutor: {assistant_response[:300]}"
        )
        title = await _call_text_model(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You write short, descriptive chat titles.",
        )
        return title.strip().strip('"\'').rstrip('.')
    except Exception:
        return user_message[:47] + "..." if len(user_message) > 50 else user_message


async def generate_tutor_response(
    messages: List[Dict[str, str]],
    latest_message: str,
    image_base64: str = None,
    about_me: Optional[str] = None,
) -> str:
    """Use Claude as an AI tutor to respond to student questions.

    If image_base64 is provided, the image is sent directly to Claude Vision
    alongside the text so Claude can actually *see* the student's homework.
    """
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

    # Use the vision dispatcher when an image is attached (better OCR on student
    # homework), the text dispatcher otherwise (faster/cheaper for plain Q&A).
    tutor_provider = _settings.ai_vision_provider if image_base64 else _settings.ai_text_provider

    logger.info(
        "[generate_tutor_response] calling provider=%s msg_count=%d has_image=%s",
        tutor_provider,
        len(claude_messages),
        bool(image_base64),
    )

    system_prompt = TUTOR_SYSTEM_PROMPT
    if about_me and about_me.strip():
        system_prompt = (
            f"STUDENT PROFILE (use this to personalize your help):\n{about_me.strip()}\n\n"
            + TUTOR_SYSTEM_PROMPT
        )

    try:
        if image_base64:
            return await _call_vision_model(messages=claude_messages, system_prompt=system_prompt)
        return await _call_text_model(messages=claude_messages, system_prompt=system_prompt)
    except Exception as e:
        logger.exception(
            "[generate_tutor_response] call failed provider=%s has_image=%s err_type=%s err=%s",
            tutor_provider,
            bool(image_base64),
            type(e).__name__,
            e,
        )
        return (
            "I'm having a little trouble connecting right now. "
            "Could you try asking your question again in a moment?"
        )
