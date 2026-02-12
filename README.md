# 🏋️ 운동 기록 분석 봇

Telegram 그룹 채팅에서 운동 기록을 자동 감지하고 전문가 수준의 분석을 제공하는 봇입니다.

## 기능
- 📸 이미지 운동 기록 자동 추출 (GPT-4o Vision)
- 📝 텍스트 운동 기록 자동 감지
- 📊 전문가 평가 및 칼로리 추정
- 📈 운동 이력 및 통계 추적

## 설정

```bash
cp .env.example .env
# .env 파일에 TELEGRAM_BOT_TOKEN과 OPENAI_API_KEY 입력

pip install -r requirements.txt
python run.py
```

## 배포 (Render)
`render.yaml`로 Background Worker로 배포하세요.

## 명령어
| 명령어 | 설명 |
|--------|------|
| `/start` | 봇 소개 |
| `/setweight 75` | 체중 설정 |
| `/history` | 최근 운동 기록 |
| `/stats` | 전체 통계 |
| `/analyze` | 마지막 기록 재분석 |
| `/help` | 도움말 |
