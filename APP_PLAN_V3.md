# OhMyPT 개발 계획 v3 — "AI 보조 + 사람 트레이너" 전환

작성일: 2026-07-24. v2(대화형 AI PT)를 대체한다. Claude·Codex·Grok 3자 토의 결론 반영.

## 1. 방향

- **AI = 보조(assistant), 코칭 = 사람 트레이너.** AI 역할 한정: 목표 설정 도움, 운동 관련 정보 제공, 인바디 기반 권장량·매크로 계산, 자연어/사진 기록의 자동 구조화·저장.
- **메인 UI = GPT/Claude 스타일 에이전트 채팅.** 모든 입력은 채팅으로. 기록 열람(식단/운동/인바디 분리, 일별 모아보기)은 부차 화면.
- **트레이너 전용 탭**: 할당된 클라이언트 기록 열람 + 이탈 리스크 큐 + 추천 발송(사람이 승인).
- **BM**: 트레이너-유저 데이터 공유 페인포인트 해결. 회원 무료, 트레이너 활성 회원 수 기준 과금. 비전 분석 쿼터로 COGS 방어.
- **InBody 연동**: LookinBody WebAPI로 측정 데이터 공식 수신(사진 판독의 상위 호환). 전략상 "납품"이 아니라 생태계 입점 → 트랙션 확보 후 제휴 논의.

## 2. 설계 원칙 (토의 합의)

1. 채팅은 **입력의 메인**이지 정보 구조 전체가 아니다. 추이·비교·트레이너 스캔은 전용 화면.
2. **모든 DB 저장은 확인 카드로 표시** — 종류·내용·수정/취소. 신뢰 = 제품.
3. 이탈 신호는 "실패 판정"이 아니라 **개입 트리거**. 트레이너 리스크 큐로 표면화, 개입은 사람.
4. AI는 개별 처방 금지. 일반 정보 + 계산 + 근거 제시까지. 추천의 최종 승인자는 트레이너.
5. 공개 순위표·스트릭 강조는 개인 화면에서 제외 (그룹 챌린지 opt-in만).

## 3. InBody(LookinBody) WebAPI 연동

조사 결과(2026-07): REST, 헤더 `Account` + `API-KEY` 인증(LookinBody Web 계정에서 발급),
조회 파라미터 UserID(지점) 또는 UserToken/전화번호(전체), 필드 WT/SMM/PBF/BMR 등.
상세 스펙은 계정 로그인 후 공개 → **어댑터를 환경변수 기반으로 구현**하고 계정 발급 후 필드 매핑 확정.

- `bot/inbody_api.py`: `LOOKINBODY_API_BASE`, `LOOKINBODY_ACCOUNT`, `LOOKINBODY_API_KEY`, `LOOKINBODY_DATA_PATH` 환경변수. 미설정 시 기능 비활성(사진 판독 폴백 유지).
- 유저 전화번호(UserToken)로 최신 측정 조회 → `inbody_records` 저장 → 권장량 재계산.
- 주의: API 이용약관의 경쟁 제품/재판매 제한 조항 확인 후 프로덕션 적용.

## 4. 신규 구성요소

| 컴포넌트 | 파일 | 내용 |
|---|---|---|
| 에이전트 코어 | `bot/agent.py` | tool-calling 루프. 도구: log_meal, log_workout, get_today_status, get_recent_history, create_goal, compute_nutrition_targets, sync_inbody |
| 채팅 저장 | `bot/database.py` | `chat_messages(user_id, role, content, cards_json)` — 단일 스레드/유저 |
| InBody 어댑터 | `bot/inbody_api.py` | LookinBody WebAPI 클라이언트 |
| 채팅 API | `bot/web.py` | `POST /api/v2/chat`(텍스트/사진), `GET /api/v2/chat/history`, `POST /api/v2/inbody/sync` |
| iOS 채팅 탭 | `ios/.../Chat*` | ChatView(메인 탭), 저장 카드 렌더링, 사진 첨부 |

사진 입력은 기존 분류·추출 파이프라인(`/api/app/upload` 내부 로직) 재사용 — LLM 루프 없이 저장 후 카드 반환 (비용 절감).

## 5. 로드맵

### Phase A — 에이전트 채팅 + InBody 어댑터 (지금)
- [x] 설계 문서
- [ ] chat_messages 테이블 + 헬퍼
- [ ] bot/agent.py tool-calling 에이전트
- [ ] bot/inbody_api.py
- [ ] /api/v2/chat, /history, /inbody/sync
- [ ] iOS: 코치 탭(채팅), 탭 재배치 (코치|오늘|기록|프로필)
- 완료 기준: 앱 채팅에 "닭가슴살 샐러드 먹었어" → 저장 카드 + 오늘 현황 반영

### Phase B — 신뢰 계층
- 저장 카드의 수정/취소 (기록 편집 API + 채팅 내 액션)
- 복수 의도 입력("점심 먹고 하체 했어") → 두 테이블 동시 기록
- AI 프롬프트·카피에서 "코치" 톤 제거 (analyzer의 certified trainer 톤 정리)

### Phase C — 인증·테넌시 (상용 전 P0)
- 공개 API 인증 (`/api/records` 등), 그룹 간 데이터 분리
- trainer_id↔client_id 명시 배정 (텔레그램 그룹 독립), 초대 코드/QR
- Apple/Google 로그인 + JWT (v2 계획 재사용)

### Phase D — 트레이너 탭 (iOS)
- 리스크 큐 (기록 공백·빈도 하락 신호, 운동/식단 분리)
- 회원 상세 통합 타임라인, AI 연락 초안 + 사람 승인 발송
- 연락 이력·다음 확인일 저장

### Phase E — BM 검증
- 트레이너 10~15명 인터뷰 (가격: 국내 경쟁 1.9만~11.9만원 앵커)
- KPI: 회원 기록률, 트레이너 주간 확인 시간, 리스크 알림 후 연락률
- 비전 분석 쿼터 + 과금

## 6. 알려진 부채 (토의에서 발굴, Phase C 전 수리)

- `/api/records` 등 무인증 공개 (web.py:773)
- X-App-Token 미설정 시 전체 허용 + user_id 신뢰 (web.py:1082)
- 적자 계산: 부분 기록을 하루 전체 섭취로 간주 (database.py:1168)
- 침묵 감지가 운동∪식단 합집합 — 도메인별 분리 필요
- 개인 DM 대상이 "최근 7일 활성"만 — 이탈 개입과 역방향 필터 (database.py:1494)
- 공개 순위표 "shame/pride ritual" (handlers.py:1920) — opt-in으로 강등 예정
