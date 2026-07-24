"""Chat assistant agent — tool-calling loop for the app's main chat UI.

Role boundary (v3 design): the AI is an *assistant*, not a coach. It structures
natural-language input into DB records, computes intake targets from InBody
data, helps set goals, and answers general fitness questions. It never issues
personalized prescriptions — that is the human trainer's job.

Every DB write a tool performs is surfaced back to the client as a "card"
({kind, title, rows, meta, ref_id}) so the app can render a confirmation with
edit/undo affordances. Trust layer > chat polish.
"""

import json
import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from bot import inbody_api
from bot.analyzer import (
    MAIN_MODEL,
    _create,
    classify_workout,
    extract_from_text,
    extract_meal_from_text,
)
from bot.database import (
    GOAL_METRICS,
    compute_target_kcal_detailed,
    create_goal,
    get_chat_history,
    get_latest_inbody,
    get_meals_for_date,
    get_recent_meals,
    get_recent_records,
    get_records_for_date,
    list_goals,
    save_chat_message,
    save_inbody,
    save_meal,
    save_record,
)

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

MAX_TOOL_ROUNDS = 4
HISTORY_TURNS = 16

AGENT_SYSTEM = (
    "당신은 피트니스 기록 앱 OhMyPT의 어시스턴트입니다. 한국어로 짧고 담백하게 답합니다.\n\n"
    "역할 (반드시 지킬 것):\n"
    "1. 기록 자동화: 사용자가 먹은 것/운동한 것을 자연어로 말하면 도구로 저장합니다. "
    "저장 결과는 카드로 표시되므로 본문에 수치를 반복하지 마세요. 한 문장 확인이면 충분합니다.\n"
    "2. 계산: 인바디 기초대사량 기반 하루 권장 섭취량과 단백질/탄수/지방 배분을 도구로 계산해 알려줍니다.\n"
    "3. 목표 설정 도움: 사용자와 대화로 목표(체중/체지방/골격근, 기한)를 구체화하고 합의되면 도구로 저장합니다. "
    "저장 전 반드시 사용자 확인을 받으세요.\n"
    "4. 정보: 운동·영양 일반 지식 질문에 답합니다. 근거 수준을 밝히고 과장하지 않습니다.\n\n"
    "금지:\n"
    "- 개인 맞춤 처방(운동 프로그램 지시, 식단 처방, 재활/의료 조언) 금지. "
    "그런 요청에는 일반 정보를 제공하되 '구체적인 프로그램은 담당 트레이너와 상의하세요'라고 안내합니다.\n"
    "- 기록에 대한 평가·훈계·죄책감 유발 금지. 기록하면 그 자체로 완료입니다.\n"
    "- 하지 않은 저장을 했다고 말하지 않기. 도구 결과에 없는 수치를 지어내지 않기.\n\n"
    "입력이 식사인지 운동인지 애매하면 짧게 물어보세요. 둘 다 포함이면 두 도구를 모두 호출하세요."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "log_meal",
            "description": "사용자가 먹은 음식을 식단 기록으로 저장한다. 음식 설명 원문을 그대로 전달할 것.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "사용자가 말한 음식 내용 원문"},
                    "meal_type": {
                        "type": "string",
                        "enum": ["breakfast", "lunch", "dinner", "snack"],
                        "description": "끼니. 사용자가 명시 안 하면 생략(시간대로 추정됨)",
                    },
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_workout",
            "description": "사용자가 수행한 운동을 기록으로 저장한다. 운동 설명 원문을 그대로 전달할 것.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "사용자가 말한 운동 내용 원문"}
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_status",
            "description": "오늘의 섭취 칼로리/매크로 합계, 권장량 대비 현황, 오늘 운동 기록을 조회한다.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_history",
            "description": "최근 운동/식단/인바디 기록 요약을 조회한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "항목 수 (기본 10)"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_goal",
            "description": "사용자와 합의된 목표를 저장한다. 반드시 사용자가 확인한 뒤에만 호출할 것.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "enum": list(GOAL_METRICS.keys()),
                        "description": "목표 지표 (weight=체중kg, body_fat_pct=체지방률%, body_fat_kg=체지방량kg, skeletal_muscle_kg=골격근량kg)",
                    },
                    "target_value": {"type": "number"},
                    "target_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["metric", "target_value", "target_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_nutrition_targets",
            "description": "최신 인바디 BMR과 활성 목표로 하루 권장 섭취 칼로리와 단백질/탄수/지방 목표를 계산한다.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sync_inbody",
            "description": "InBody(LookinBody) 공식 API에서 사용자의 최신 체성분 측정을 가져와 저장한다. 전화번호 필요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "InBody 측정 시 등록한 전화번호"}
                },
                "required": ["phone"],
            },
        },
    },
]


def _today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _meal_type_by_time() -> str:
    hour = datetime.now(KST).hour
    if hour < 10:
        return "breakfast"
    if hour < 15:
        return "lunch"
    if hour < 21:
        return "dinner"
    return "snack"


def _fmt(value, unit: str = "", digits: int = 0) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{number:,.{digits}f}"
    return f"{text}{unit}"


# --- Tool implementations -------------------------------------------------


async def _tool_log_meal(user_id: int, chat_id: int, args: dict) -> dict:
    description = (args.get("description") or "").strip()
    if not description:
        return {"ok": False, "error": "음식 설명이 비어 있습니다."}
    meal_type = args.get("meal_type") or _meal_type_by_time()
    lock = bool(args.get("meal_type"))
    date = _today()

    data = await extract_meal_from_text(description, meal_type, lock_to_default=lock)
    meals_by_type = data.get("meals_by_type") or {}
    if not meals_by_type:
        return {"ok": False, "error": "음식 내용을 인식하지 못했습니다."}

    cards = []
    total_kcal = 0.0
    for mtype, meal in meals_by_type.items():
        if not isinstance(meal, dict):
            continue
        kcal = meal.get("total_kcal") or meal.get("estimated_kcal")
        macros = {
            "protein_g": meal.get("protein_g"),
            "carbs_g": meal.get("carbs_g"),
            "fat_g": meal.get("fat_g"),
        }
        meal_id = save_meal(
            chat_id, user_id, date, mtype,
            raw_input=description,
            structured_md=meal.get("summary_md") or description,
            estimated_kcal=kcal,
            macros=macros,
            analysis=meal.get("analysis_md") or "",
        )
        if kcal:
            total_kcal += float(kcal)
        type_ko = {"breakfast": "아침", "lunch": "점심", "dinner": "저녁", "snack": "간식"}.get(mtype, mtype)
        cards.append({
            "kind": "meal",
            "ref_id": meal_id,
            "title": f"식사 기록 · {type_ko}",
            "rows": [
                ["내용", (meal.get("summary_md") or description)[:120]],
                ["칼로리", _fmt(kcal, " kcal")],
                ["단백질/탄수/지방", f"{_fmt(macros['protein_g'],'g')} / {_fmt(macros['carbs_g'],'g')} / {_fmt(macros['fat_g'],'g')}"],
            ],
            "meta": date,
        })

    day_meals = get_meals_for_date(user_id, date)
    day_total = sum(float(m["estimated_kcal"] or 0) for m in day_meals)
    target = compute_target_kcal_detailed(user_id, date)
    target_kcal = target.get("target_kcal")
    summary = f"오늘 합계 {_fmt(day_total, ' kcal')}"
    if target_kcal:
        summary += f" / 권장 {_fmt(target_kcal, ' kcal')}"

    return {"ok": True, "saved_kcal": total_kcal, "day_summary": summary, "cards": cards}


async def _tool_log_workout(user_id: int, chat_id: int, args: dict) -> dict:
    description = (args.get("description") or "").strip()
    if not description:
        return {"ok": False, "error": "운동 설명이 비어 있습니다."}
    date = _today()

    structured = await extract_from_text(description)
    if not structured or "NO_WORKOUT_DATA" in structured:
        return {"ok": False, "error": "운동 내용을 인식하지 못했습니다."}

    category = classify_workout(structured)
    record_id = save_record(
        chat_id, user_id,
        raw_input=description,
        structured_md=structured,
        analysis="",
        estimated_kcal=None,
        date=date,
        category=category,
    )
    return {
        "ok": True,
        "cards": [{
            "kind": "workout",
            "ref_id": record_id,
            "title": f"운동 기록 · {category or '기타'}",
            "rows": [["내용", structured[:160]]],
            "meta": date,
        }],
    }


async def _tool_get_today_status(user_id: int, chat_id: int, args: dict) -> dict:
    date = _today()
    meals = get_meals_for_date(user_id, date)
    records = get_records_for_date(user_id, date)
    target = compute_target_kcal_detailed(user_id, date)
    intake = sum(float(m["estimated_kcal"] or 0) for m in meals)
    protein = sum(float(m["protein_g"] or 0) for m in meals)
    return {
        "date": date,
        "intake_kcal": round(intake),
        "protein_g": round(protein),
        "target_kcal": target.get("target_kcal"),
        "target_macros": target.get("macros"),
        "meals": [
            {"type": m["meal_type"], "kcal": m["estimated_kcal"], "items": (m["structured_md"] or "")[:100]}
            for m in meals
        ],
        "workouts": [
            {"category": r.get("category"), "summary": (r.get("structured_md") or "")[:100]}
            for r in records
        ],
    }


async def _tool_get_recent_history(user_id: int, chat_id: int, args: dict) -> dict:
    limit = int(args.get("limit") or 10)
    records = get_recent_records(chat_id, user_id, limit=limit)
    meals = get_recent_meals(user_id, limit=limit)
    latest_inbody = get_latest_inbody(user_id)
    goals = list_goals(user_id)
    return {
        "workouts": [
            {"date": r["date"], "category": r.get("category"), "summary": (r.get("structured_md") or "")[:80]}
            for r in records
        ],
        "meals": [
            {"date": m["date"], "type": m["meal_type"], "kcal": m["estimated_kcal"]}
            for m in meals
        ],
        "latest_inbody": {
            "measured_at": latest_inbody.get("measured_at"),
            "weight_kg": latest_inbody.get("weight_kg"),
            "skeletal_muscle_kg": latest_inbody.get("skeletal_muscle_kg"),
            "body_fat_pct": latest_inbody.get("body_fat_pct"),
            "bmr_kcal": latest_inbody.get("bmr_kcal"),
        } if latest_inbody else None,
        "active_goals": [
            {"metric": g["metric"], "target_value": g["target_value"], "target_date": g["target_date"]}
            for g in goals
        ],
    }


async def _tool_set_goal(user_id: int, chat_id: int, args: dict) -> dict:
    metric = args.get("metric")
    try:
        target_value = float(args.get("target_value"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "target_value가 숫자가 아닙니다."}
    target_date = (args.get("target_date") or "").strip()
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        return {"ok": False, "error": "target_date는 YYYY-MM-DD 형식이어야 합니다."}

    latest = get_latest_inbody(user_id)
    start_value = None
    if latest:
        start_value = {
            "weight": latest.get("weight_kg"),
            "body_fat_pct": latest.get("body_fat_pct"),
            "body_fat_kg": latest.get("body_fat_kg"),
            "skeletal_muscle_kg": latest.get("skeletal_muscle_kg"),
        }.get(metric)

    goal_id = create_goal(
        user_id=user_id, chat_id=chat_id, metric=metric,
        start_value=start_value, target_value=target_value, target_date=target_date,
    )
    label_unit = GOAL_METRICS.get(metric, (metric, ""))
    metric_label = f"{label_unit[0]} ({label_unit[1]})" if label_unit[1] else label_unit[0]
    return {
        "ok": True,
        "cards": [{
            "kind": "goal",
            "ref_id": goal_id,
            "title": "목표 저장",
            "rows": [
                ["지표", str(metric_label)],
                ["현재 → 목표", f"{_fmt(start_value, '', 1)} → {_fmt(target_value, '', 1)}"],
                ["기한", target_date],
            ],
            "meta": _today(),
        }],
    }


async def _tool_compute_nutrition_targets(user_id: int, chat_id: int, args: dict) -> dict:
    date = _today()
    target = compute_target_kcal_detailed(user_id, date)
    if not target.get("target_kcal"):
        return {
            "ok": False,
            "error": target.get("reasoning_md") or "인바디(BMR) 정보가 없어 계산할 수 없습니다. 인바디 사진을 올리거나 InBody 연동을 사용하세요.",
        }
    macros = target.get("macros") or {}
    card = {
        "kind": "targets",
        "ref_id": None,
        "title": "하루 권장 섭취량",
        "rows": [
            ["기초대사량", _fmt(target.get("bmr"), " kcal")],
            ["TDEE", _fmt(target.get("tdee"), " kcal")],
            ["권장 섭취", _fmt(target.get("target_kcal"), " kcal")],
            ["단백질/탄수/지방", f"{_fmt(macros.get('protein_g'),'g')} / {_fmt(macros.get('carbs_g'),'g')} / {_fmt(macros.get('fat_g'),'g')}"],
        ],
        "meta": date,
    }
    return {"ok": True, "detail": {k: target.get(k) for k in ("target_kcal", "bmr", "tdee", "days_left", "source")}, "macros": macros, "cards": [card]}


async def _tool_sync_inbody(user_id: int, chat_id: int, args: dict) -> dict:
    if not inbody_api.is_configured():
        return {"ok": False, "error": "InBody 공식 연동이 아직 활성화되지 않았습니다. 인바디 결과지 사진을 올려주시면 판독해서 저장할게요."}
    phone = (args.get("phone") or "").strip()
    try:
        measurements = await inbody_api.fetch_measurements(phone)
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    if not measurements:
        return {"ok": False, "error": "해당 전화번호로 조회된 측정 데이터가 없습니다."}

    latest = measurements[0]
    measured_at = str(latest.get("measured_at") or _today())
    raw_json = latest.pop("raw_json", "")
    inbody_id = save_inbody(chat_id, user_id, measured_at, latest, raw_json=raw_json)
    return {
        "ok": True,
        "cards": [{
            "kind": "inbody",
            "ref_id": inbody_id,
            "title": "인바디 동기화 (공식 데이터)",
            "rows": [
                ["측정일", measured_at[:16]],
                ["체중 / 골격근 / 체지방률", f"{_fmt(latest.get('weight_kg'),'',1)} / {_fmt(latest.get('skeletal_muscle_kg'),'',1)} / {_fmt(latest.get('body_fat_pct'),'%',1)}"],
                ["기초대사량", _fmt(latest.get("bmr_kcal"), " kcal")],
            ],
            "meta": measured_at[:10],
        }],
    }


TOOL_IMPL = {
    "log_meal": _tool_log_meal,
    "log_workout": _tool_log_workout,
    "get_today_status": _tool_get_today_status,
    "get_recent_history": _tool_get_recent_history,
    "set_goal": _tool_set_goal,
    "compute_nutrition_targets": _tool_compute_nutrition_targets,
    "sync_inbody": _tool_sync_inbody,
}


def _profile_context(user_id: int) -> str:
    """Small always-injected context: latest inbody + active goals + today totals."""
    parts = []
    latest = get_latest_inbody(user_id)
    if latest:
        parts.append(
            f"최신 인바디({str(latest.get('measured_at'))[:10]}): "
            f"체중 {latest.get('weight_kg')}kg, 골격근 {latest.get('skeletal_muscle_kg')}kg, "
            f"체지방률 {latest.get('body_fat_pct')}%, BMR {latest.get('bmr_kcal')}kcal"
        )
    goals = list_goals(user_id)
    for g in goals[:3]:
        parts.append(f"활성 목표: {g['metric']} → {g['target_value']} (기한 {g['target_date']})")
    if not parts:
        parts.append("등록된 인바디/목표 없음.")
    return "\n".join(parts)


async def run_agent_turn(user_id: int, chat_id: int, user_text: str) -> dict:
    """One chat turn: persist user msg, run tool loop, persist reply.

    Returns {reply_md, cards: [...]}. Cards accumulate from every tool call
    that produced them, in call order.
    """
    save_chat_message(user_id, "user", user_text)

    history = get_chat_history(user_id, limit=HISTORY_TURNS)
    messages = [
        {"role": "system", "content": AGENT_SYSTEM},
        {"role": "system", "content": f"[사용자 컨텍스트]\n{_profile_context(user_id)}\n오늘: {_today()}"},
    ]
    for msg in history:
        if msg["role"] in ("user", "assistant") and msg.get("content"):
            messages.append({"role": msg["role"], "content": msg["content"]})

    cards: list[dict] = []
    reply_md = ""

    for _round in range(MAX_TOOL_ROUNDS):
        resp = await _create(
            model=MAIN_MODEL,
            messages=messages,
            tools=TOOLS,
            max_completion_tokens=4000,
        )
        choice = resp.choices[0].message
        tool_calls = choice.tool_calls or []

        if not tool_calls:
            reply_md = (choice.content or "").strip()
            break

        messages.append({
            "role": "assistant",
            "content": choice.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except ValueError:
                args = {}
            impl = TOOL_IMPL.get(name)
            if impl is None:
                result = {"ok": False, "error": f"unknown tool {name}"}
            else:
                try:
                    result = await impl(user_id, chat_id, args)
                except Exception as e:  # tool crash must not kill the turn
                    logger.exception(f"Agent tool {name} failed")
                    result = {"ok": False, "error": f"도구 실행 오류: {e}"}
            for card in result.get("cards") or []:
                cards.append(card)
            # Cards render client-side; strip from what the model re-reads.
            slim = {k: v for k, v in result.items() if k != "cards"}
            if result.get("cards"):
                slim["saved_cards"] = [c["title"] for c in result["cards"]]
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(slim, ensure_ascii=False),
            })
    else:
        reply_md = "요청을 처리했지만 정리 중 문제가 있었어요. 기록 탭에서 확인해주세요."

    if not reply_md:
        reply_md = "저장했어요." if cards else "무슨 뜻인지 잘 모르겠어요. 다시 말씀해주시겠어요?"

    save_chat_message(
        user_id, "assistant", reply_md,
        cards_json=json.dumps(cards, ensure_ascii=False) if cards else None,
    )
    return {"reply_md": reply_md, "cards": cards}
