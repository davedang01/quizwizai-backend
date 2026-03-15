import uuid
import random
from datetime import datetime
from typing import List, Dict, Any


SUBJECT_POOLS = {
    "Mathematics": {
        "topics": ["Fractions", "Decimals", "Word Problems", "Algebra", "Geometry"],
        "content": "This is extracted content from the uploaded material about Mathematics including fundamental concepts and practical applications."
    },
    "Science": {
        "topics": ["Physics", "Chemistry", "Biology", "Earth Science"],
        "content": "This is extracted content from the uploaded material about Science including experimental procedures and scientific principles."
    },
    "History": {
        "topics": ["Ancient Civilizations", "Medieval Period", "Modern Era", "World Wars"],
        "content": "This is extracted content from the uploaded material about History including key events and historical figures."
    },
    "English": {
        "topics": ["Grammar", "Literature", "Reading Comprehension", "Writing"],
        "content": "This is extracted content from the uploaded material about English language and literature."
    },
    "Computer Science": {
        "topics": ["Programming", "Data Structures", "Algorithms", "Web Development"],
        "content": "This is extracted content from the uploaded material about Computer Science and software development."
    }
}

DIFFICULTY_LEVELS = ["Easy", "Medium", "Hard"]

MULTIPLE_CHOICE_QUESTIONS = [
    {
        "text": "What is the capital of France?",
        "options": ["London", "Paris", "Berlin", "Madrid"],
        "correct_answer": "Paris"
    },
    {
        "text": "What is 15 × 3?",
        "options": ["35", "45", "55", "65"],
        "correct_answer": "45"
    },
    {
        "text": "Which planet is closest to the sun?",
        "options": ["Venus", "Mercury", "Earth", "Mars"],
        "correct_answer": "Mercury"
    },
    {
        "text": "What is the chemical symbol for gold?",
        "options": ["Go", "Au", "Ag", "Gd"],
        "correct_answer": "Au"
    },
    {
        "text": "Who wrote Romeo and Juliet?",
        "options": ["Christopher Marlowe", "William Shakespeare", "Ben Jonson", "John Webster"],
        "correct_answer": "William Shakespeare"
    },
    {
        "text": "What is the largest ocean on Earth?",
        "options": ["Atlantic Ocean", "Indian Ocean", "Arctic Ocean", "Pacific Ocean"],
        "correct_answer": "Pacific Ocean"
    }
]

WORD_PROBLEM_QUESTIONS = [
    {
        "text": "John has 5 apples and Mary gives him 3 more. How many apples does John have now?",
        "correct_answer": "8"
    },
    {
        "text": "A book costs $12 and you have $50. How much change will you get back?",
        "correct_answer": "38"
    },
    {
        "text": "If a car travels 60 miles in 1 hour, how far will it travel in 3 hours?",
        "correct_answer": "180"
    },
    {
        "text": "Sarah has twice as many pencils as Tom. If Tom has 7 pencils, how many does Sarah have?",
        "correct_answer": "14"
    },
    {
        "text": "A recipe calls for 2 cups of flour for every 1 cup of sugar. If you use 3 cups of sugar, how much flour do you need?",
        "correct_answer": "6"
    }
]

FILL_BLANK_QUESTIONS = [
    {
        "text": "The capital of Japan is ______.",
        "correct_answer": "Tokyo"
    },
    {
        "text": "Water boils at 100 degrees ______.",
        "correct_answer": "Celsius"
    },
    {
        "text": "Photosynthesis is the process by which plants convert ______ into glucose.",
        "correct_answer": "light"
    },
    {
        "text": "The Great Wall of China is located in ______.",
        "correct_answer": "China"
    },
    {
        "text": "A triangle has ______ sides.",
        "correct_answer": "three"
    }
]

MATH_PROBLEMS = [
    {
        "text": "Solve: 2x + 5 = 13",
        "correct_answer": "4"
    },
    {
        "text": "What is 12% of 250?",
        "correct_answer": "30"
    },
    {
        "text": "Calculate: (5 + 3) × 2 - 1",
        "correct_answer": "15"
    },
    {
        "text": "What is the square root of 144?",
        "correct_answer": "12"
    },
    {
        "text": "If y = 2x - 3, what is y when x = 5?",
        "correct_answer": "7"
    }
]


async def analyze_content(text_or_base64: str) -> Dict[str, Any]:
    """Stubbed AI service: analyze uploaded content and extract information"""
    subject = random.choice(list(SUBJECT_POOLS.keys()))
    subject_data = SUBJECT_POOLS[subject]

    return {
        "id": str(uuid.uuid4()),
        "content_text": subject_data["content"],
        "subject": subject,
        "topics": random.sample(subject_data["topics"], k=min(3, len(subject_data["topics"]))),
        "difficulty": random.choice(DIFFICULTY_LEVELS),
        "num_pages": random.randint(1, 5),
        "created_at": datetime.utcnow().isoformat()
    }


async def generate_questions(
    content_text: str,
    test_type: str,
    difficulty: str,
    num_questions: int
) -> List[Dict[str, Any]]:
    """Stubbed AI service: generate test questions based on type and difficulty"""
    questions = []

    if test_type == "Multiple Choice":
        pool = MULTIPLE_CHOICE_QUESTIONS
        for i in range(min(num_questions, len(pool))):
            q = random.choice(pool)
            questions.append({
                "id": str(uuid.uuid4()),
                "type": "multiple_choice",
                "text": q["text"],
                "options": q["options"],
                "correct_answer": q["correct_answer"],
                "difficulty": difficulty
            })

    elif test_type == "Word Problems":
        pool = WORD_PROBLEM_QUESTIONS
        for i in range(min(num_questions, len(pool))):
            q = random.choice(pool)
            questions.append({
                "id": str(uuid.uuid4()),
                "type": "word_problem",
                "text": q["text"],
                "correct_answer": q["correct_answer"],
                "difficulty": difficulty
            })

    elif test_type == "Math Problems":
        pool = MATH_PROBLEMS
        for i in range(min(num_questions, len(pool))):
            q = random.choice(pool)
            questions.append({
                "id": str(uuid.uuid4()),
                "type": "math",
                "text": q["text"],
                "correct_answer": q["correct_answer"],
                "difficulty": difficulty
            })

    elif test_type == "Fill in the Blank":
        pool = FILL_BLANK_QUESTIONS
        for i in range(min(num_questions, len(pool))):
            q = random.choice(pool)
            questions.append({
                "id": str(uuid.uuid4()),
                "type": "fill_blank",
                "text": q["text"],
                "correct_answer": q["correct_answer"],
                "difficulty": difficulty
            })

    else:  # Mixed
        pools = [MULTIPLE_CHOICE_QUESTIONS, WORD_PROBLEM_QUESTIONS, MATH_PROBLEMS, FILL_BLANK_QUESTIONS]
        types = ["multiple_choice", "word_problem", "math", "fill_blank"]

        for i in range(num_questions):
            pool_idx = i % len(pools)
            pool = pools[pool_idx]
            q_type = types[pool_idx]
            q = random.choice(pool)

            if q_type == "multiple_choice":
                questions.append({
                    "id": str(uuid.uuid4()),
                    "type": q_type,
                    "text": q["text"],
                    "options": q["options"],
                    "correct_answer": q["correct_answer"],
                    "difficulty": difficulty
                })
            else:
                questions.append({
                    "id": str(uuid.uuid4()),
                    "type": q_type,
                    "text": q["text"],
                    "correct_answer": q["correct_answer"],
                    "difficulty": difficulty
                })

    return questions


def grade_answer(question: Dict[str, Any], user_answer: str) -> bool:
    """Grade a user's answer by simple comparison (case-insensitive for text)"""
    correct = question.get("correct_answer", "").strip().lower()
    user = user_answer.strip().lower()
    return user == correct


async def generate_study_guide(wrong_answers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Stubbed AI service: generate study guide for incorrect answers"""
    study_guide = []

    study_tips = [
        "Review the fundamental concepts related to this topic.",
        "Practice similar problems to build your understanding.",
        "Break down the problem into smaller, manageable parts.",
        "Refer to textbook examples for clarification.",
        "Work with a study partner to discuss the concept.",
        "Watch tutorial videos on this topic.",
        "Take notes on key definitions and formulas.",
        "Create a mind map to visualize relationships."
    ]

    for answer in wrong_answers:
        study_guide.append({
            "question_id": answer.get("question_id"),
            "topic": answer.get("topic", "General"),
            "explanation": random.choice(study_tips),
            "resource_link": "https://example.com/study",
            "difficulty_adjustment": random.choice(["Keep at same level", "Try easier problems first", "Increase difficulty gradually"])
        })

    return study_guide


async def generate_flashcards(content_text: str, num_cards: int, additional_prompts: str = None) -> List[Dict[str, str]]:
    """Stubbed AI service: generate flashcard pairs from content"""
    flashcard_pairs = [
        {
            "front": "What is the capital of France?",
            "back": "Paris is the capital of France and serves as its largest city."
        },
        {
            "front": "Define mitochondria",
            "back": "The mitochondria is the powerhouse of the cell, responsible for producing ATP through cellular respiration."
        },
        {
            "front": "What does photosynthesis do?",
            "back": "Photosynthesis is the process where plants convert light energy, water, and carbon dioxide into glucose and oxygen."
        },
        {
            "front": "Who wrote the Declaration of Independence?",
            "back": "Thomas Jefferson was the primary author of the Declaration of Independence, adopted on July 4, 1776."
        },
        {
            "front": "What is the formula for the area of a circle?",
            "back": "The area of a circle is calculated as A = πr², where r is the radius of the circle."
        },
        {
            "front": "Define photosynthesis",
            "back": "The biochemical process by which plants use sunlight to synthesize glucose from carbon dioxide and water."
        },
        {
            "front": "What is the periodic table?",
            "back": "A systematic arrangement of all known chemical elements organized by atomic number and chemical properties."
        },
        {
            "front": "Who was the first President of the United States?",
            "back": "George Washington served as the first President of the United States from 1789 to 1797."
        },
        {
            "front": "What is the Pythagorean theorem?",
            "back": "In a right triangle, the square of the hypotenuse equals the sum of squares of the other two sides: a² + b² = c²."
        },
        {
            "front": "Define osmosis",
            "back": "The movement of water molecules across a semipermeable membrane from an area of high water concentration to low water concentration."
        }
    ]

    cards = []
    for i in range(min(num_cards, len(flashcard_pairs))):
        pair = flashcard_pairs[i]
        cards.append(pair)

    return cards


async def generate_study_guide_entry(question: str, user_answer: str, correct_answer: str) -> Dict[str, str]:
    """Stubbed AI service: generate explanation and tips for a wrong answer"""
    explanations = [
        "This question tests your understanding of fundamental concepts. The correct answer emphasizes the importance of this principle.",
        "This is a common misconception. The key difference is understanding how these concepts relate to each other.",
        "Pay attention to the specific wording of the question. The answer depends on the precise definition provided.",
        "This topic requires connecting multiple concepts together. Review how they work in combination.",
        "The correct answer reflects real-world application of this concept. Practice with similar scenarios."
    ]

    tips = [
        "Review similar examples in your textbook and practice applying the same logic.",
        "Break down the problem into smaller parts and solve each step carefully.",
        "Create flashcards for key definitions and formulas related to this topic.",
        "Work through practice problems with a study partner and discuss your reasoning.",
        "Watch educational videos explaining this concept from different angles.",
        "Write out the step-by-step solution process and identify where you went wrong.",
        "Compare the wrong answer with the correct answer to understand the difference.",
        "Memorize key formulas and definitions related to this topic."
    ]

    practice_questions = [
        "Can you explain this concept in your own words?",
        "How does this concept apply to a real-world situation?",
        "Can you solve a similar problem with different numbers?",
        "What would happen if you changed one variable in this problem?",
        "How does this topic connect to what you learned previously?"
    ]

    return {
        "explanation": random.choice(explanations),
        "tips": random.choice(tips),
        "practice_question": random.choice(practice_questions)
    }


async def generate_tutor_response(messages: List[Dict[str, str]], latest_message: str) -> str:
    """Stubbed AI service: generate a tutoring-style response from AI tutor"""
    tutor_responses = {
        "default": [
            "Great question! Let me help you understand this better. The key concept here is that we need to break down the problem into smaller parts. Can you tell me which part you found most confusing?",
            "That's a really important topic to understand. I can help you with that! Think about it this way: what do you already know about this subject? Let's build on that foundation.",
            "I appreciate your curiosity! This topic involves several steps. Let me explain the first one: [explanation]. Does that make sense so far?",
            "Good thinking! You're on the right track. However, there's an important detail to consider. Can you think about what might be different about this situation?"
        ],
        "math": [
            "Nice approach! Let me help you with the calculation. The first step is to identify what we're solving for. Have you set up the equation correctly?",
            "This math problem requires us to follow these steps in order. First, let's simplify the expression. What do you get when you combine like terms?",
            "Good attempt! Let's check your work step by step. Did you remember to apply the order of operations correctly?"
        ],
        "science": [
            "Excellent curiosity about this scientific concept! Remember that science is about cause and effect. What do you think causes this phenomenon?",
            "This is a fundamental principle in science. Think about the relationship between these two variables. How do they interact with each other?",
            "Great observation! In science, we need to understand the 'why' behind things. Can you think about what mechanism is at work here?"
        ],
        "history": [
            "History is full of interesting causes and effects. For this event, it's important to understand the context of the time. What factors do you think led to this happening?",
            "That's a thought-provoking question about history! Let's look at this from different perspectives. What motivated the people involved in this event?"
        ],
        "english": [
            "Great literary analysis! Remember that authors choose their words carefully. What effect do you think this word choice has on the reader?",
            "This is an interesting interpretation of the text. Can you find specific evidence from the passage that supports your thinking?"
        ]
    }

    message_lower = latest_message.lower()
    response_key = "default"

    if any(word in message_lower for word in ["solve", "calculate", "equation", "math", "number", "formula"]):
        response_key = "math"
    elif any(word in message_lower for word in ["science", "experiment", "physics", "chemistry", "biology", "force", "energy"]):
        response_key = "science"
    elif any(word in message_lower for word in ["history", "historical", "event", "war", "civilization", "date"]):
        response_key = "history"
    elif any(word in message_lower for word in ["english", "literature", "book", "author", "poem", "character", "writing"]):
        response_key = "english"

    responses = tutor_responses.get(response_key, tutor_responses["default"])
    return random.choice(responses)
