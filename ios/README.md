# OhMyPT iOS

Native SwiftUI client for the OhMyPersonalTrainer backend.

## Requirements

- macOS with Xcode installed
- Homebrew
- XcodeGen

## Build and Run

```bash
cd ios
brew install xcodegen
xcodegen generate
open OhMyPT.xcodeproj
```

In Xcode, select the `OhMyPT` scheme and run it on an iOS 16+ simulator or device.

## First Launch Settings

Open the app and enter:

- `서버 URL`: defaults to `https://workoutbot-ybbz.onrender.com`
- `텔레그램 user_id`: your numeric Telegram user ID
- `앱 토큰`: optional. Enter this only if the backend is configured with `APP_API_TOKEN`.

The Today and Records tabs load only after a non-empty server URL and valid integer `user_id` are saved.

## Backend Endpoints

Default base URL:

```text
https://workoutbot-ybbz.onrender.com
```

Used by the app:

```text
GET  /api/app/summary?user_id=<int>
GET  /api/records?user_id=<int>&limit=50
POST /api/app/upload          (multipart: photo, user_id, caption)
POST /api/app/record          (JSON: user_id, text, analyze?)
POST /api/app/plan            (JSON: user_id, refresh?)
POST /api/app/daily-summary   (JSON: user_id, refresh?)
```

If `앱 토큰` is non-empty, the app sends it as:

```text
X-App-Token: <token>
```

## Features

- **오늘**: 칼로리/매크로/목표 적자, 플랜·요약 생성, 사진/텍스트 기록 바로가기
- **기록**: 주간 운동 칼로리 차트(Swift Charts), 기록 목록·상세
- **사진 업로드**: 카메라/앨범 → 서버 자동 분류(운동/식단/인바디) → 분석 결과
- **텍스트 기록**: 운동·식단 텍스트 저장 (선택 시 코치 분석)

