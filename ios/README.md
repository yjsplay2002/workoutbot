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
GET /api/app/summary?user_id=<int>
GET /api/records?user_id=<int>&limit=20
```

If `앱 토큰` is non-empty, the app sends it as:

```text
X-App-Token: <token>
```

