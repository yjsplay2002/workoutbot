# 🏋️ 운동 기록 분석 봇

Telegram + 웹 대시보드. 운동·인바디·식단을 모두 기록하고 목표 달성까지 AI가 코칭합니다.

## 기능
- 📸 운동 기록 이미지/텍스트 자동 분석 (GPT 비전 모델)
- 📏 인바디 사진 → 체중·골격근량·체지방률·BMR 등 자동 추출 및 추이 저장
- 🎯 목표 CRUD (체중·체지방률·골격근량 등 병렬 관리, 주 목표 지정)
- 📅 LLM 기반 일일 칼로리 계산 + 아침/점심/저녁 식단 추천
- 🍽️ 식단 텍스트/사진 분석 (칼로리·단탄지 추출)
- 🌙 매일 21:00 KST 자동 일일 요약 + 목표 달성 평가 (그룹 채팅 푸시)
- 🌐 웹 대시보드: 목표 카드·인바디 추이·일일 계획·식단 일지

## 설정

```bash
cp .env.example .env
# .env에 TELEGRAM_BOT_TOKEN, OPENAI_API_KEY (필수)
# 선택: MAIN_MODEL (기본 gpt-5.5), VISION_MODEL (기본은 MAIN_MODEL과 동일)

pip install -r requirements.txt
python run.py
```

## 배포 (Render)
`render.yaml`로 Docker 웹 서비스 배포. `data/` 디스크에 SQLite 영구 저장.

## 주요 명령어
| 명령어 | 설명 |
|--------|------|
| `/start`, `/help` | 봇 소개 / 도움말 |
| `/setweight 75`, `/setheight 175` | 체중·키 설정 |
| `/inbody` | 인바디 사진 분석 (캡션 또는 답장) |
| `/breakfast`, `/lunch`, `/dinner`, `/snack` | 식단 기록 (텍스트 또는 사진) |
| `/goal add 체중 75 2026-08-01` | 목표 추가 |
| `/goal list / primary [ID] / done [ID] / del [ID]` | 목표 관리 |
| `/plan` | 오늘의 권장 칼로리·식단 (LLM) |
| `/today` | 오늘 요약 미리보기 |
| `/history`, `/stats`, `/analyze` | 운동 기록 조회·재분석 |
| `/settrainer`, `/unsettrainer` | 트레이너 지정 (관리자) |

## 환경 변수
| 변수 | 기본 | 설명 |
|------|------|------|
| `TELEGRAM_BOT_TOKEN` | (필수) | BotFather 토큰 |
| `OPENAI_API_KEY` | (필수) | OpenAI 키 |
| `MAIN_MODEL` | `gpt-5.5` | 텍스트 분석/계획/요약용 메인 LLM |
| `VISION_MODEL` | `MAIN_MODEL` | 이미지 분석용 모델 (별도로 분리하고 싶을 때) |
| `WEB_PORT` | `8080` | 대시보드 포트 |
| `WEB_URL` | `http://localhost:8080` | 텔레그램 로그인 위젯 콜백 URL |
| `DB_PATH` | `data/workout.db` | SQLite 경로 |
