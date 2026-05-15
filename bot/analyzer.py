import base64
import json
import os
import re
from typing import Optional

from openai import AsyncOpenAI

client: Optional[AsyncOpenAI] = None

MAIN_MODEL = os.environ.get("MAIN_MODEL", "gpt-5.5")
VISION_MODEL = os.environ.get("VISION_MODEL", MAIN_MODEL)
# Cheap fast model for intent routing. Override via env if you want a smaller/faster one.
CLASSIFIER_MODEL = os.environ.get("CLASSIFIER_MODEL", MAIN_MODEL)


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


async def extract_from_image(image_bytes: bytes, user_caption: str = "") -> str:
    b64 = base64.b64encode(image_bytes).decode()
    c = get_client()
    user_content: list = [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        {"type": "text", "text": "이 이미지에서 운동 기록을 추출해주세요. 날짜가 있다면 정확히 읽어주세요. 2자리 연도(예: 26)는 2026년입니다."},
    ]
    if user_caption:
        user_content.append({
            "type": "text",
            "text": (
                f"사용자가 사진과 함께 보낸 메모 (사진에 없는 세트·횟수·무게 등 추가 정보일 수 있음):\n"
                f"{user_caption}\n\n"
                "이미지와 메모를 종합하여 운동을 추출하세요. 메모에 세트·횟수·무게가 명시되어 있고 "
                "사진에 그 운동기구나 환경이 보이면 메모의 수치를 사용하세요. 메모만으로 운동이 명확하면 메모 기준으로 추출해도 됩니다."
            ),
        })
    resp = await c.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        max_completion_tokens=1500,
    )
    return resp.choices[0].message.content or ""


async def extract_from_text(text: str) -> str:
    c = get_client()
    resp = await c.chat.completions.create(
        model=MAIN_MODEL,
        messages=[
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": text},
        ],
        max_completion_tokens=1500,
    )
    return resp.choices[0].message.content or ""


async def analyze_workout(structured_md: str, weight_kg: Optional[float] = None, history_summary: str = "", height_cm: Optional[float] = None) -> str:
    weight_info = f"사용자 체중: {weight_kg}kg" if weight_kg else "사용자 체중: 미설정 (70-75kg 남성 기준으로 추정)"
    if height_cm:
        weight_info += f", 키: {height_cm}cm"
    history_info = f"\n\n최근 운동 이력:\n{history_summary}" if history_summary else ""

    c = get_client()
    resp = await c.chat.completions.create(
        model=MAIN_MODEL,
        messages=[
            {"role": "system", "content": ANALYSIS_SYSTEM},
            {
                "role": "user",
                "content": f"{weight_info}{history_info}\n\n오늘의 운동 기록:\n{structured_md}",
            },
        ],
        max_completion_tokens=2500,
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


def group_by_date(extractions: list[str], fallback_date: Optional[str] = None) -> dict[str, list[str]]:
    """Group extracted workout data by date. Returns {date: [data1, data2, ...]}.

    fallback_date should be the message's send date in the user's timezone (KST);
    used when an extracted record has no DATE line.
    """
    from datetime import datetime
    groups: dict[str, list[str]] = {}
    if fallback_date is None:
        fallback_date = datetime.now().strftime("%Y-%m-%d")

    for text in extractions:
        date = extract_date(text) or fallback_date
        clean = strip_date_line(text)
        if clean:
            groups.setdefault(date, []).append(clean)

    return groups


CATEGORY_KEYWORDS = {
    "upper": [
        "bench", "press", "row", "curl", "pulldown", "pullup", "pull-up", "pushup", "push-up",
        "fly", "raise", "tricep", "bicep", "chest", "shoulder", "lat", "delt",
        "벤치", "프레스", "로우", "컬", "풀다운", "풀업", "푸쉬업", "푸시업",
        "플라이", "레이즈", "삼두", "이두", "가슴", "어깨", "등",
        "체스트", "숄더", "랫", "백",
    ],
    "lower": [
        "squat", "deadlift", "leg", "lunge", "calf", "hip", "glute", "hack",
        "스쿼트", "데드리프트", "레그", "런지", "종아리", "힙", "글루트", "핵",
        "하체", "대퇴", "허벅지",
    ],
    "core": [
        "plank", "pallof", "crunch", "ab wheel", "ab rollout", "back extension",
        "dead bug", "sit-up", "situp",
        "플랭크", "크런치", "복근", "코어", "데드버그",
    ],
    "cardio": [
        "run", "running", "bike", "cycling", "rowing machine", "treadmill", "cardio",
        "elliptical", "stairmaster", "jogging",
        "러닝", "달리기", "자전거", "트레드밀", "유산소", "조깅",
    ],
}

CATEGORY_COLORS = {
    "상체": "#3498db",
    "하체": "#e74c3c",
    "코어": "#f1c40f",
    "유산소": "#2ecc71",
    "전신": "#9b59b6",
}


def classify_workout(structured_md: str) -> str:
    """Classify workout into categories based on keywords."""
    if not structured_md:
        return "기타"
    text_lower = structured_md.lower()

    found = set()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                found.add(category)
                break

    if not found:
        return "기타"

    # Check for "extension" separately — could be leg extension (lower) or back extension (core)
    if "extension" in text_lower and "leg" in text_lower:
        found.add("lower")
    if "back extension" in text_lower:
        found.add("core")
        found.discard("upper")  # back extension is core, not upper

    labels = {
        "upper": "상체",
        "lower": "하체",
        "core": "코어",
        "cardio": "유산소",
    }

    if "upper" in found and "lower" in found:
        parts = ["전신"]
        if "core" in found:
            parts.append("코어")
        if "cardio" in found:
            parts.append("유산소")
        return " + ".join(parts) if len(parts) > 1 else parts[0]

    result = []
    for key in ["upper", "lower", "core", "cardio"]:
        if key in found:
            result.append(labels[key])

    return " + ".join(result) if result else "기타"


def get_category_color(category: str) -> str:
    """Get the primary color for a workout category."""
    for key, color in CATEGORY_COLORS.items():
        if key in category:
            return color
    return "#888888"


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


# ── InBody extraction ────────────────────────────────────────

INBODY_SYSTEM = (
    "You are an InBody body composition analyzer. "
    "Extract measurements from this InBody (체성분 분석) image and return STRICT JSON only. "
    "All numeric fields use float values (no units in the value). "
    "If a field is not visible, omit it from the JSON.\n\n"
    "Required schema:\n"
    "{\n"
    '  "measured_at": "YYYY-MM-DD or null",\n'
    '  "weight_kg": float,\n'
    '  "skeletal_muscle_kg": float,  // 골격근량\n'
    '  "body_fat_kg": float,  // 체지방량\n'
    '  "body_fat_pct": float,  // 체지방률 (%)\n'
    '  "bmi": float,\n'
    '  "bmr_kcal": float,  // 기초대사량\n'
    '  "body_water_kg": float,  // 체수분\n'
    '  "protein_kg": float,\n'
    '  "mineral_kg": float,\n'
    '  "visceral_fat_level": float\n'
    "}\n\n"
    "Date hint: two-digit years like '26' mean 2026. Default to 2026 if year is ambiguous.\n"
    "If the image is NOT an InBody / body composition sheet, reply exactly: NOT_INBODY"
)


async def extract_inbody(image_bytes: bytes, user_caption: str = "") -> dict:
    """Extract InBody metrics from an image. Returns dict or {} if invalid."""
    b64 = base64.b64encode(image_bytes).decode()
    c = get_client()
    user_content: list = [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        {"type": "text", "text": "이 인바디 이미지에서 측정값을 JSON으로만 추출하세요."},
    ]
    if user_caption:
        user_content.append({
            "type": "text",
            "text": f"사용자 메모 (측정일·체중 등 부가 정보일 수 있음): {user_caption}",
        })
    resp = await c.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {"role": "system", "content": INBODY_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        max_completion_tokens=600,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or ""
    if "NOT_INBODY" in content:
        return {}
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', content, re.DOTALL)
        if not m:
            return {}
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


# ── Meal extraction ──────────────────────────────────────────

MEAL_SYSTEM = (
    "You are a Korean nutritionist. The user may log one OR several meals in a single message. "
    "Read both the photo (if any) AND the caption/text to figure out what they ate, when they ate it, "
    "and split into meal_type groups. Return STRICT JSON only.\n\n"
    "Photo cases:\n"
    "  (a) Plate/lunchbox/bowl/snack — extract visible food\n"
    "  (b) Menu board / restaurant menu / kiosk / delivery-app screenshot / receipt — "
    "      the user did NOT necessarily eat everything; use the caption to identify what they ordered. "
    "      If kcal is printed on the menu, USE that exact number (mark source='menu').\n"
    "  (c) Nutrition label / food package — combine with caption to identify portion eaten\n"
    "  (d) No photo, text only — extract foods from the text\n\n"
    "Meal-grouping rules:\n"
    "  - If the user explicitly labels meals in the caption (e.g. '아침 X', '점심 Y', '저녁 Z', "
    "    '간식'), split into those meal_types.\n"
    "  - If only one meal is described, return one entry; pick its meal_type from any time-of-day "
    "    word in caption ('아침에', '저녁으로', etc.) — otherwise use the provided default_meal_type.\n"
    "  - If the caption explicitly references the photo (e.g. '첨부 메뉴판에서 치킨 샐러드 파스타 "
    "    칼로리 찾아서 점심에 반영해줘'), match THAT item from the menu and assign to the meal_type "
    "    the caption says.\n"
    "  - Partial-consumption hints ('반만 먹었어', '한 입만') → scale down kcal/macros for that item.\n\n"
    "Schema:\n"
    "{\n"
    '  "meals_by_type": {\n'
    '    "<meal_type>": {   // meal_type ∈ "breakfast" | "lunch" | "dinner" | "snack"\n'
    '      "items": [\n'
    '        {"name": str, "amount": str, "kcal": int,\n'
    '         "protein_g": float, "carbs_g": float, "fat_g": float,\n'
    '         "source": "menu" | "image" | "caption"}\n'
    "      ],\n"
    '      "total_kcal": int,\n'
    '      "protein_g": float,\n'
    '      "carbs_g": float,\n'
    '      "fat_g": float,\n'
    '      "summary_md": "<b>식단</b>...HTML 짧은 요약 (Korean, <b>, <i>, • bullets, no markdown, no tables)",\n'
    '      "analysis_md": "<b>영양 평가</b>...HTML 분석 + 개선 추천 (Korean, 4-6 lines)"\n'
    "    },\n"
    "    ...other meal_types if present...\n"
    "  }\n"
    "}\n\n"
    "Each item's source:\n"
    "  - 'menu':    matched from menu/label printed kcal — kcal authoritative\n"
    "  - 'image':   identified directly from food photo — kcal estimated\n"
    "  - 'caption': identified from user's text only — kcal estimated\n\n"
    "If the message has explicit single-meal LOCK (system tells you 'lock_to_default'), put ALL "
    "items under that single meal_type and ignore other meal labels in the caption.\n\n"
    "If you cannot identify any food from either image or caption: {\"meals_by_type\": {}}"
)


async def extract_meal_from_image(image_bytes: bytes, default_meal_type: str, user_ctx: str = "", lock_to_default: bool = False) -> dict:
    """Returns {meals_by_type: {<meal_type>: {...}}}.

    default_meal_type: fallback meal_type when caption doesn't specify when the user ate.
    lock_to_default: if True, force ALL items under default_meal_type (used by /breakfast etc.).
    """
    import logging
    log = logging.getLogger(__name__)
    b64 = base64.b64encode(image_bytes).decode()
    c = get_client()
    lock_note = f"lock_to_default=YES — 모든 음식을 '{default_meal_type}' 한 끼니로만 분류하세요." if lock_to_default else ""
    user_text = (
        f"default_meal_type: {default_meal_type}\n"
        f"{lock_note}\n"
        f"{user_ctx}\n\n"
        "이 사진(과 캡션)에서 사용자가 무엇을 먹었는지 분석해주세요."
    )
    resp = await c.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {"role": "system", "content": MEAL_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": user_text},
                ],
            },
        ],
        max_completion_tokens=1500,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or ""
    data = _safe_json(raw)
    if not data or not data.get("meals_by_type"):
        log.warning(f"extract_meal_from_image returned no meals. raw={raw[:600]!r}")
    return data


async def extract_meal_from_text(text: str, default_meal_type: str, user_ctx: str = "", lock_to_default: bool = False) -> dict:
    import logging
    log = logging.getLogger(__name__)
    c = get_client()
    lock_note = f"lock_to_default=YES — 모든 음식을 '{default_meal_type}' 한 끼니로만 분류하세요." if lock_to_default else ""
    prompt = (
        f"default_meal_type: {default_meal_type}\n"
        f"{lock_note}\n"
        f"{user_ctx}\n\n"
        f"식단 내용:\n{text}"
    )
    resp = await c.chat.completions.create(
        model=MAIN_MODEL,
        messages=[
            {"role": "system", "content": MEAL_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=1500,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or ""
    data = _safe_json(raw)
    if not data or not data.get("meals_by_type"):
        log.warning(f"extract_meal_from_text returned no meals. raw={raw[:600]!r}")
    return data


def _safe_json(content: str) -> dict:
    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', content, re.DOTALL)
        if not m:
            return {}
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


# ── Daily plan / summary ─────────────────────────────────────

PLAN_SYSTEM = (
    "You are a certified Korean fitness coach and nutritionist. "
    "The user's daily kcal and macro targets are PRE-COMPUTED and provided in context — "
    "your job is to design specific meals that hit those targets, not to recompute them.\n\n"
    "Return STRICT JSON only with this schema:\n"
    "{\n"
    '  "target_kcal_intake": int,    // mirror the provided target (do not recompute)\n'
    '  "target_kcal_burn": int,      // recommended workout calorie burn for today\n'
    '  "macros": {\n'
    '    "protein_g": int, "carbs_g": int, "fat_g": int\n'
    "  },\n"
    '  "meals": {\n'
    '    "breakfast": {\n'
    '      "kcal": int, "protein_g": int, "carbs_g": int, "fat_g": int,\n'
    '      "title": "식단 한줄 요약 (예: 오트밀 + 그릭요거트 + 계란)",\n'
    '      "items": [\n'
    '        {"name": "오트밀", "amount": "60g", "kcal": 220, "protein_g": 7, "carbs_g": 40, "fat_g": 4}\n'
    "      ],\n"
    '      "notes_md": "선택사항: 조리·대체 음식 메모 (HTML)"\n'
    "    },\n"
    '    "lunch":  { ... 동일 구조 ... },\n'
    '    "dinner": { ... 동일 구조 ... },\n'
    '    "snack":  { ... 선택사항 (간식 필요시) ... }\n'
    "  },\n"
    '  "rationale_md": "전체 식단 설계 의도 + 운동 가이드 (HTML, 4-7줄)"\n'
    "}\n\n"
    "Rules:\n"
    "- Each meal's kcal/P/C/F should be specific to the foods listed in items[].\n"
    "- Sum of meals (excluding snack overlap) should approximately match target_kcal_intake (±10%) and macros.\n"
    "- Use specific Korean-context foods with realistic portion sizes (grams, 컵, 개수). 일반인이 한국에서 쉽게 구할 수 있는 재료.\n"
    "- Adjust meal composition by direction: 감량(cut)이면 단백질·채소 위주, 증량(bulk)이면 탄수 비중 증가, 근비대(muscle-gain)면 단백질+탄수.\n"
    "- HTML only for *_md fields (<b>, <i>, •, <br>). No markdown, no tables.\n"
    "- All text in Korean."
)


async def generate_daily_plan(context_md: str) -> dict:
    c = get_client()
    resp = await c.chat.completions.create(
        model=MAIN_MODEL,
        messages=[
            {"role": "system", "content": PLAN_SYSTEM},
            {"role": "user", "content": context_md},
        ],
        max_completion_tokens=1500,
        response_format={"type": "json_object"},
    )
    return _safe_json(resp.choices[0].message.content or "")


SUMMARY_SYSTEM = (
    "You are a certified Korean fitness coach. Generate the user's end-of-day report based on the day's "
    "workout records, meals, and active goals.\n\n"
    "Return STRICT JSON only:\n"
    "{\n"
    '  "summary_md": "오늘 운동+식단 종합 요약. HTML (<b>, •, <i>). 4-8 lines. Korean.",\n'
    '  "goal_assessment_md": "활성 목표별로 오늘 진행 여부 평가. 잘된 점/부족한 점/내일 권장 사항. HTML, 4-8 lines."\n'
    "}"
)


async def generate_daily_summary(context_md: str) -> dict:
    c = get_client()
    resp = await c.chat.completions.create(
        model=MAIN_MODEL,
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM},
            {"role": "user", "content": context_md},
        ],
        max_completion_tokens=1400,
        response_format={"type": "json_object"},
    )
    return _safe_json(resp.choices[0].message.content or "")


# ── Intent classification ────────────────────────────────────

INTENT_CLASSIFIER_SYSTEM = (
    "You are a fitness assistant intent classifier. The user is in a fitness coaching context. "
    "Given a photo or text from the user, decide what kind of fitness log it is. "
    "Return STRICT JSON only.\n\n"
    "Schema:\n"
    "{\n"
    '  "intent": "workout" | "meal" | "inbody" | "unrelated",\n'
    '  "meal_type": "breakfast" | "lunch" | "dinner" | "snack" | null,\n'
    '  "confidence": 0.0..1.0,\n'
    '  "reason_md": "Korean, one short sentence. Why this category."\n'
    "}\n\n"
    "Categories:\n"
    "- workout: 운동 기록. Exercise log/journal — sets, reps, weights, exercise names. "
    "Includes handwritten gym notebooks (even if hard to read), gym whiteboards, "
    "screenshots from fitness apps (Strong, Hevy, MyFitnessPal workout tab), workout text descriptions.\n"
    "- meal: 식단. Includes:\n"
    "    • Food photo: plate, bowl, lunchbox, snack, restaurant dish\n"
    "    • Menu board / restaurant menu / kiosk screen / delivery-app screenshot — especially "
    "      when the caption names a specific item the user ordered\n"
    "    • Nutrition label / food package\n"
    "    • Food/recipe text descriptions\n"
    "  meal_type optional — set it if obvious from caption (e.g. '아침 먹었어') or current "
    "  time-of-day context; otherwise null.\n"
    "- inbody: 인바디. Body composition analysis sheet — InBody/Olympus/Tanita output showing "
    "weight, skeletal muscle, body fat %, BMR, BMI, etc. Usually a printout with bar charts.\n"
    "- unrelated: anything else — pets, scenery, screenshots of unrelated chat, code, memes, "
    "documents, selfies without context, etc.\n\n"
    "Be decisive even if the image quality is poor. If it looks like a workout log in any form "
    "(handwriting, smudges, partial visibility), classify as workout — the downstream extractor "
    "will handle illegibility separately. Same for food and inbody."
)


async def classify_intent_from_image(image_bytes: bytes, hint: str = "") -> dict:
    b64 = base64.b64encode(image_bytes).decode()
    c = get_client()
    user_text = "이 사진을 분류해주세요." + (f"\n참고: {hint}" if hint else "")
    resp = await c.chat.completions.create(
        model=CLASSIFIER_MODEL,
        messages=[
            {"role": "system", "content": INTENT_CLASSIFIER_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": user_text},
                ],
            },
        ],
        max_completion_tokens=400,
        response_format={"type": "json_object"},
    )
    return _safe_json(resp.choices[0].message.content or "")


async def classify_intent_from_text(text: str, hint: str = "") -> dict:
    c = get_client()
    user_text = f"다음 텍스트를 분류해주세요:\n\n{text}" + (f"\n\n참고: {hint}" if hint else "")
    resp = await c.chat.completions.create(
        model=CLASSIFIER_MODEL,
        messages=[
            {"role": "system", "content": INTENT_CLASSIFIER_SYSTEM},
            {"role": "user", "content": user_text},
        ],
        max_completion_tokens=400,
        response_format={"type": "json_object"},
    )
    return _safe_json(resp.choices[0].message.content or "")


FITNESS_RELEVANT_KEYWORDS = [
    # workout
    "운동", "세트", "set", "rep", "kg", "횟수", "벤치", "스쿼트", "데드", "덤벨", "바벨",
    "풀업", "푸쉬업", "푸시업", "플랭크", "랫풀", "레그", "숄더", "컬", "런지", "로우",
    "프레스", "인클라인", "오버헤드", "케이블", "머신",
    "bench", "squat", "deadlift", "press", "curl", "pull", "rm", "reps",
    # meal/food
    "아침", "점심", "저녁", "간식", "밥", "닭", "샐러드", "단백질", "탄수", "지방",
    "고구마", "계란", "두부", "스테이크", "샌드위치", "샐러드", "스무디", "쉐이크",
    "kcal", "칼로리", "그램", "g당", "먹었", "먹음", "식단", "도시락",
    "breakfast", "lunch", "dinner", "snack", "meal", "protein", "carbs",
    # inbody
    "인바디", "골격근", "체지방", "체중", "근육량", "기초대사", "bmr", "bmi",
    "체수분", "내장지방",
]


def is_fitness_relevant_text(text: str) -> bool:
    """Cheap keyword pre-filter to gate LLM intent classification on text.

    True if any workout/meal/inbody-adjacent keyword appears, OR the text contains
    a numeric pattern that looks like sets/reps/weights/calories. False for chitchat.
    Keeps the LLM classifier from running on every random group-chat message.
    """
    if not text:
        return False
    t = text.strip()
    if len(t) < 3:
        return False
    tl = t.lower()
    if any(kw.lower() in tl for kw in FITNESS_RELEVANT_KEYWORDS):
        return True
    # Numeric patterns that strongly suggest fitness logs
    if re.search(r'\d+\s*[xX×]\s*\d+', t):
        return True
    if re.search(r'\d+\s*kg', tl):
        return True
    if re.search(r'\d+\s*(kcal|cal|칼로리)', tl):
        return True
    return False
