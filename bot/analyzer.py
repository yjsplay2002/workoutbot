import base64
import os
import re
from typing import Optional

from openai import AsyncOpenAI

client: Optional[AsyncOpenAI] = None


def get_client() -> AsyncOpenAI:
    global client
    if client is None:
        client = AsyncOpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            timeout=120.0,
        )
    return client


EXTRACT_SYSTEM = (
    "You are a fitness data extraction expert. "
    "Extract all workout exercises from this input. "
    "For each exercise, identify: exercise name (Korean + English abbreviation), sets, reps, weight (kg). "
    "Output as a numbered list like:\n"
    "1. 운동명 (English) — Set1: 무게kg×횟수, Set2: 무게kg×횟수, ...\n"
    "Do NOT use markdown tables. Use plain numbered lists only.\n"
    "If no workout data is found, reply exactly: NO_WORKOUT_DATA"
)

ANALYSIS_SYSTEM = (
    "You are a certified personal trainer and exercise physiologist. "
    "Analyze the following workout record from an expert perspective. "
    "Structure your reply in Korean with these sections:\n\n"
    "🏋️ <b>구조화된 기록</b>\n(include the workout list)\n\n"
    "📊 <b>운동 전문가 평가</b>\n(exercise selection and programming quality)\n\n"
    "📈 <b>빈도/강도 평가</b>\n(frequency and intensity assessment)\n\n"
    "🔥 <b>칼로리 소모 추정</b>\n(estimated kcal — state the number clearly, e.g. '추정 칼로리: 약 XXX kcal')\n\n"
    "💡 <b>종합 추천</b>\n(overall recommendations)\n\n"
    "IMPORTANT FORMATTING RULES:\n"
    "- Do NOT use markdown (no #, **, ```, |)\n"
    "- Use HTML tags only: <b>bold</b>, <i>italic</i>\n"
    "- Use bullet points with • or numbered lists\n"
    "- Do NOT use tables. Use lists instead.\n"
    "- Keep lines short for mobile readability.\n"
    "Reply entirely in Korean."
)

WORKOUT_KEYWORDS = [
    "운동", "세트", "set", "rep", "kg", "횟수", "벤치프레스", "스쿼트",
    "데드리프트", "덤벨", "바벨", "풀업", "푸쉬업", "푸시업", "플랭크",
    "랫풀다운", "레그프레스", "숄더프레스", "컬", "런지", "로우",
    "인클라인", "디클라인", "오버헤드", "케이블", "머신",
    "bench", "squat", "deadlift", "press", "curl", "pull",
    "RM", "rm", "1rm", "reps",
]


def is_workout_text(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    # Need at least 2 keyword matches or a pattern like "NxN" or "Nkg"
    matches = sum(1 for kw in WORKOUT_KEYWORDS if kw.lower() in text_lower)
    has_pattern = bool(re.search(r'\d+\s*[xX×]\s*\d+', text)) or bool(re.search(r'\d+\s*kg', text_lower))
    return matches >= 2 or (matches >= 1 and has_pattern)


async def extract_from_image(image_bytes: bytes) -> str:
    b64 = base64.b64encode(image_bytes).decode()
    c = get_client()
    resp = await c.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": EXTRACT_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": "이 이미지에서 운동 기록을 추출해주세요."},
                ],
            },
        ],
        max_tokens=1500,
    )
    return resp.choices[0].message.content or ""


async def extract_from_text(text: str) -> str:
    c = get_client()
    resp = await c.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": text},
        ],
        max_tokens=1500,
    )
    return resp.choices[0].message.content or ""


async def analyze_workout(structured_md: str, weight_kg: Optional[float] = None, history_summary: str = "") -> str:
    weight_info = f"사용자 체중: {weight_kg}kg" if weight_kg else "사용자 체중: 미설정 (70-75kg 남성 기준으로 추정)"
    history_info = f"\n\n최근 운동 이력:\n{history_summary}" if history_summary else ""

    c = get_client()
    resp = await c.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": ANALYSIS_SYSTEM},
            {
                "role": "user",
                "content": f"{weight_info}{history_info}\n\n오늘의 운동 기록:\n{structured_md}",
            },
        ],
        max_tokens=2500,
    )
    return resp.choices[0].message.content or ""


def extract_kcal(analysis: str) -> Optional[float]:
    """Try to extract kcal number from analysis text."""
    patterns = [
        r'약\s*(\d+)\s*kcal',
        r'(\d+)\s*kcal',
        r'(\d+)\s*칼로리',
    ]
    for p in patterns:
        m = re.search(p, analysis)
        if m:
            return float(m.group(1))
    return None
