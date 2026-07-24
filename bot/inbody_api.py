"""LookinBody WebAPI adapter — official InBody measurement sync.

The detailed endpoint spec is only visible after logging into a LookinBody Web
account (https://apikr.lookinbody.com). What is public: REST, auth via
`Account` + `API-KEY` request headers, lookups by UserToken (phone number,
global) or UserID (per-location), body-composition fields like WT/SMM/PBF/BMR.

This adapter therefore keeps the endpoint path and field mapping configurable
so it can be finalized once an API key is issued, without code changes:

  LOOKINBODY_API_BASE   e.g. https://apikr.lookinbody.com  (default)
  LOOKINBODY_ACCOUNT    LookinBody Web account (header `Account`)
  LOOKINBODY_API_KEY    issued key (header `API-KEY`)
  LOOKINBODY_DATA_PATH  data endpoint path (default /InBodyData)

When unconfigured, is_configured() is False and callers fall back to photo
OCR (extract_inbody).
"""

import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

API_BASE = os.environ.get("LOOKINBODY_API_BASE", "https://apikr.lookinbody.com")
ACCOUNT = os.environ.get("LOOKINBODY_ACCOUNT", "")
API_KEY = os.environ.get("LOOKINBODY_API_KEY", "")
DATA_PATH = os.environ.get("LOOKINBODY_DATA_PATH", "/InBodyData")

# Field-name candidates per canonical key. LookinBody payloads use terse codes
# (WT, SMM, PBF, BMR ...) but casing/nesting may differ per region — first
# match wins, keys compared case-insensitively.
FIELD_CANDIDATES: dict[str, list[str]] = {
    "weight_kg": ["WT", "Weight", "TotalWeight"],
    "skeletal_muscle_kg": ["SMM", "SkeletalMuscleMass"],
    "body_fat_kg": ["BFM", "BodyFatMass"],
    "body_fat_pct": ["PBF", "PercentBodyFat"],
    "bmi": ["BMI"],
    "bmr_kcal": ["BMR", "BasalMetabolicRate"],
    "body_water_kg": ["TBW", "TotalBodyWater"],
    "protein_kg": ["Protein"],
    "mineral_kg": ["Mineral", "Minerals"],
    "visceral_fat_level": ["VFL", "VFA", "VisceralFatLevel"],
    "measured_at": ["TestDate", "DateTimes", "Datetimes", "TestDatetimes"],
}


def is_configured() -> bool:
    return bool(ACCOUNT and API_KEY)


def _headers() -> dict:
    return {
        "Account": ACCOUNT,
        "API-KEY": API_KEY,
        "Content-Type": "application/json",
    }


def _pick(record: dict, candidates: list[str]):
    lowered = {str(k).lower(): v for k, v in record.items()}
    for cand in candidates:
        if cand.lower() in lowered:
            return lowered[cand.lower()]
    return None


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def map_measurement(record: dict) -> dict:
    """Map one raw LookinBody measurement to inbody_records columns."""
    mapped: dict = {"raw_json": json.dumps(record, ensure_ascii=False)}
    for column, candidates in FIELD_CANDIDATES.items():
        value = _pick(record, candidates)
        mapped[column] = value if column == "measured_at" else _to_float(value)
    return mapped


def _extract_records(payload) -> list[dict]:
    """Payload shape varies (list, or dict wrapping a list) — dig out dicts."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("InBodyData", "Data", "data", "Result", "result", "rows"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return [r for r in inner if isinstance(r, dict)]
            if isinstance(inner, dict):
                return [inner]
        # Flat single-measurement dict
        if any(_pick(payload, c) is not None for c in FIELD_CANDIDATES.values()):
            return [payload]
    return []


async def test_connection() -> bool:
    """POST /user/test — documented connectivity check."""
    if not is_configured():
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{API_BASE}/user/test", headers=_headers())
            return resp.status_code == 200
    except httpx.HTTPError as e:
        logger.warning(f"LookinBody connection test failed: {e}")
        return False


async def fetch_measurements(user_token: str) -> list[dict]:
    """Fetch measurements for a member by UserToken (phone number).

    Returns mapped dicts (inbody_records columns), newest first when the API
    provides dates. Raises RuntimeError with a user-safe message on failure.
    """
    if not is_configured():
        raise RuntimeError("InBody 연동이 아직 설정되지 않았습니다. (LOOKINBODY_ACCOUNT/API_KEY)")

    token = "".join(ch for ch in user_token if ch.isdigit())
    if not token:
        raise RuntimeError("전화번호 형식이 올바르지 않습니다.")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{API_BASE}{DATA_PATH}",
                headers=_headers(),
                json={"UserToken": token},
            )
    except httpx.HTTPError as e:
        logger.error(f"LookinBody request failed: {e}")
        raise RuntimeError("InBody 서버에 연결하지 못했습니다.")

    if resp.status_code == 401:
        raise RuntimeError("InBody API 인증 실패 — API 키를 확인하세요.")
    if resp.status_code != 200:
        logger.error(f"LookinBody HTTP {resp.status_code}: {resp.text[:300]}")
        raise RuntimeError(f"InBody API 오류 (HTTP {resp.status_code})")

    try:
        payload = resp.json()
    except ValueError:
        raise RuntimeError("InBody 응답을 해석할 수 없습니다.")

    records = _extract_records(payload)
    mapped = [map_measurement(r) for r in records]
    mapped.sort(key=lambda m: str(m.get("measured_at") or ""), reverse=True)
    return mapped
