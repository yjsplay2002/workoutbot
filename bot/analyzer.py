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
    "IMPORTANT: First identify the DATE of the workout.\n"
    "Date formats you may see in images:\n"
    "- '26.1.27' means 2026-01-27 (YY.M.DD format)\n"
    "- '26.02.03' means 2026-02-03\n"
    "- '2026.01.24' means 2026-01-24\n"
    "- '1/24' or '01/24' with context of year 2026\n"
    "ASSUME the year is 2026 unless explicitly stated otherwise.\n"
    "Two-digit years like '26' mean 2026, NOT 1926 or 2023.\n\n"
    "Output format:\n"
    "DATE: YYYY-MM-DD\n"
    "1. 운동명 (English) — Set1: 무게kg×횟수, Set2: 무게kg×횟수, ...\n\n"
    "The DATE line is mandatory. If no date is found, use DATE: UNKNOWN\n"
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
                    {"type": "text", "text": "이 이미지에서 운동 기록을 추출해주세요. 날짜가 있다면 정확히 읽어주세요. 2자리 연도(예: 26)는 2026년입니다."},
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


def _fix_year(year_str: str) -> str:
    """Fix 2-digit or wrong years to 2026."""
    y = int(year_str)
    if y < 100:  # 2-digit year like 26
        y += 2000
    if y < 2024 or y > 2030:  # likely wrong, default to 2026
        y = 2026
    return str(y)


def extract_date(text: str) -> Optional[str]:
    """Extract DATE: YYYY-MM-DD from extraction result."""
    # YYYY-MM-DD
    m = re.search(r'DATE:\s*(\d{2,4})-(\d{1,2})-(\d{1,2})', text)
    if m:
        year = _fix_year(m.group(1))
        return f"{year}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # YYYY.MM.DD
    m = re.search(r'DATE:\s*(\d{2,4})\.(\d{1,2})\.(\d{1,2})', text)
    if m:
        year = _fix_year(m.group(1))
        return f"{year}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # YYYY/MM/DD
    m = re.search(r'DATE:\s*(\d{2,4})/(\d{1,2})/(\d{1,2})', text)
    if m:
        year = _fix_year(m.group(1))
        return f"{year}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def strip_date_line(text: str) -> str:
    """Remove the DATE: line from extracted text."""
    return re.sub(r'DATE:.*\n?', '', text).strip()


def group_by_date(extractions: list[str]) -> dict[str, list[str]]:
    """Group extracted workout data by date. Returns {date: [data1, data2, ...]}."""
    from datetime import datetime
    groups: dict[str, list[str]] = {}
    today = datetime.now().strftime("%Y-%m-%d")

    for text in extractions:
        date = extract_date(text) or today
        clean = strip_date_line(text)
        if clean:
            groups.setdefault(date, []).append(clean)

    return groups


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
