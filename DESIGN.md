---
name: OhMyPT
description: 운동·식단·인바디를 공항 웨이파인딩 사인 시스템으로 안내하는 개인 피트니스 트래커
colors:
  schiphol-yellow: "#FFC900"
  yellow-deep: "#E9B800"
  yellow-ink: "#665000"
  jet-black: "#0E0E0D"
  panel-raised: "#242422"
  panel-line: "#3A3A37"
  concrete: "#EDEDE9"
  sheet-white: "#FFFFFF"
  sheet-inset: "#F4F4F0"
  ink: "#151513"
  ink-muted: "#5D5D57"
  on-panel: "#FFFFFF"
  on-panel-muted: "#B8B8B0"
  border: "#D9D9D2"
  green: "#0E7A3C"
  amber-text: "#9A6B00"
  red: "#C42B1C"
typography:
  gate:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, sans-serif"
    fontSize: "clamp(2.2rem, 6vw, 4.6rem)"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, sans-serif"
    fontSize: "1.55rem"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "-0.015em"
  title:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, sans-serif"
    fontSize: "1.08rem"
    fontWeight: 800
    letterSpacing: "-0.01em"
  value:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Pretendard Variable, Pretendard, -apple-system, sans-serif"
    fontSize: "0.78rem"
    fontWeight: 600
rounded:
  chip: "5px"
  inset: "7px"
  surface: "10px"
  track: "4px"
spacing:
  xs: "10px"
  sm: "14px"
  md: "20px"
  cell: "16px 18px"
components:
  signband:
    backgroundColor: "{colors.schiphol-yellow}"
    textColor: "{colors.jet-black}"
    rounded: "{rounded.surface}"
    padding: "18px 20px"
  signband-hover:
    backgroundColor: "{colors.yellow-deep}"
  board:
    backgroundColor: "{colors.jet-black}"
    textColor: "{colors.on-panel}"
    rounded: "{rounded.surface}"
  sheet:
    backgroundColor: "{colors.sheet-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.surface}"
    padding: "20px"
  inset:
    backgroundColor: "{colors.sheet-inset}"
    rounded: "{rounded.inset}"
    padding: "12px 14px"
  button-primary:
    backgroundColor: "{colors.jet-black}"
    textColor: "{colors.on-panel}"
    rounded: "{rounded.inset}"
    padding: "9px 20px"
  button-primary-hover:
    backgroundColor: "{colors.panel-raised}"
  input:
    backgroundColor: "{colors.sheet-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.inset}"
    padding: "9px 12px"
  badge:
    backgroundColor: "{colors.schiphol-yellow}"
    textColor: "{colors.jet-black}"
    rounded: "{rounded.chip}"
    padding: "2px 8px"
  navlink-active:
    backgroundColor: "{colors.schiphol-yellow}"
    textColor: "{colors.jet-black}"
---

# Design System: OhMyPT

## Overview

**Creative North Star: "터미널 옐로 웨이파인딩" (국제공항 사인 시스템)**

개인 피트니스 기록을 공항 웨이파인딩으로 안내하는 세계. 목표는 게이트이고, 오늘 할 일은 다음 결정 지점이다. 다크 네온 피트니스 대시보드 문법을 명시적으로 거부한다. 화면은 세 가지 표면 재질로 구성된다: 스키폴 옐로 안내 밴드(목표·웨이파인딩 전용), 제트블랙 데이터 보드(숫자 전광판), 화이트 시트(일반 콘텐츠) — 이 셋이 콘크리트 그라운드 위에 놓인다. 장식 대신 방향성: 모든 이동 가능한 표면은 모서리에 고정된 화살표 픽토그램으로 끝난다.

숫자가 주인공이다. 전역 `font-feature-settings:"tnum"`으로 모든 숫자는 타뷸러이며, 핵심 지표는 기념비 스케일(`.gate`, clamp 2.2–4.6rem)로 게이트 표지판처럼 읽힌다. 폰트는 Pretendard 단일 패밀리(웹 CDN; iOS는 시스템 Apple SD Gothic Neo — Pretendard가 이 폰트의 대체재로 설계된 동일 보이스)이고 위계는 굵기(800 vs 600)와 크기만으로 만든다.

적용 범위: 웹은 base.html·dashboard·login이 풀 커밋 상태이며, 나머지 템플릿(records/goals/inbody/meals/report/trainer/user)은 공유 클래스+팔레트로 1차 마이그레이션된 상태다. iOS(SwiftUI, ios/OhMyPT)는 동일 시각 언어를 Theme.swift로 이식 중(두 표면 통일 룩 결정). seed key 7d2b41e4.

**Key Characteristics:**
- 세 표면 재질: 옐로 사인밴드 / 제트블랙 보드 / 화이트 시트 — 콘크리트(#EDEDE9) 그라운드 위
- 옐로는 목표·안내에만 — 장식·상태 표시에 쓰지 않음
- 기념비 스케일 타뷸러 숫자, 굵기 800 위계
- 흑백 인셋 픽토그램(SVG 스프라이트, 컬러 아이콘 없음)
- 모서리 고정 화살표 = 이동 가능함의 유일한 신호
- 그림자 없음 — 재질 대비와 1px 보더로만 깊이 표현

## Colors

옐로 하나가 안내를 독점하고, 나머지는 무채색 재질 + 소량의 시맨틱 신호로 절제된 팔레트.

### Primary
- **스키폴 옐로** (#FFC900): 목표·웨이파인딩 전용. 주 목표 사인밴드 배경, 활성 네비 링크, 트레이너 배지, 블랙 보드 위 핵심 숫자·프로그레스 필, 텍스트 선택(::selection), 캘린더 오늘 하이라이트(#FFC9002E 틴트). 이 외 용도 금지.
- **옐로 딥** (#E9B800): 사인밴드 hover 상태 전용.
- **옐로 잉크** (#665000): 옐로 배경 위 보조 텍스트(사인밴드 .sub) 전용.

### Neutral
- **제트블랙** (#0E0E0D): 데이터 보드·네비게이션 바·픽토그램 타일 배경. 카테고리 칩도 이 색(analyzer.py CATEGORY_COLORS — 전 카테고리 단일 흑색).
- **패널 레이즈드** (#242422): 보드 내부의 한 단계 밝은 면 — 보드 위 트랙 배경, 블랙 버튼 hover.
- **패널 라인** (#3A3A37): 보드 셀 사이 1px 구분선.
- **콘크리트** (#EDEDE9): 페이지 그라운드(body 배경).
- **시트 화이트** (#FFFFFF): 일반 콘텐츠 카드 배경.
- **시트 인셋** (#F4F4F0): 시트 안의 한 단계 가라앉은 면(inset, content-box), hover 배경.
- **잉크** (#151513): 기본 텍스트. **잉크 뮤트** (#5D5D57): 보조 텍스트·미분류 카테고리 폴백.
- **온패널** (#FFFFFF) / **온패널 뮤트** (#B8B8B0): 블랙 보드 위 텍스트·라벨.
- **보더** (#D9D9D2): 화이트 시트의 1px 외곽선·테이블 행 구분.

### Semantic (신호등)
- **녹** (#0E7A3C): 달성·정상. 텍스트와 트랙 필(.fill.ok)에 사용. 칩 배경은 8% 틴트(#0E7A3C14).
- **앰버 텍스트** (#9A6B00): 주의·중간 구간. 밝은 배경에서 읽히도록 어둡게 설계된 앰버. 틴트 #9A6B0014.
- **적** (#C42B1C): 초과·위험·일요일. 트랙 필(.fill.bad), 경고 아이콘. 틴트 #C42B1C12.
- 블랙 보드 위에서는 시맨틱을 밝힌 변형을 쓴다: 녹 → #7BD8A0, 적 → #FF7A6B (어두운 배경 대비 확보).

### Named Rules
**The Yellow-Is-Wayfinding Rule.** 옐로는 목표와 안내(다음 결정 지점)에만 쓴다. 상태 표시는 신호등 3색, 장식은 존재하지 않는다. 옐로가 흔해지는 순간 사인 시스템이 죽는다.

**The On-Panel Shift Rule.** 시맨틱 색은 표면에 따라 두 벌이다 — 밝은 표면에서는 어두운 원색(#0E7A3C/#C42B1C), 제트블랙 보드 위에서는 밝힌 변형(#7BD8A0/#FF7A6B). 같은 hex를 두 표면에 재사용하지 않는다.

**The Monochrome Chip Rule.** 운동 카테고리 칩은 전부 제트블랙(#0E0E0D), 미분류만 잉크 뮤트(#5D5D57)다. 카테고리별 컬러 코딩을 하지 않는다.

## Typography

**Display/Body Font:** Pretendard Variable (Pretendard, -apple-system, "Segoe UI" 폴백; 웹 CDN)
**iOS:** 시스템 Apple SD Gothic Neo — Pretendard가 이 폰트의 대체재로 설계된 동일 보이스, 별도 번들 없이 통일 룩 성립

**Character:** 휴머니스트 산세리프 단일 패밀리. 위계는 굵기 800/600/400과 스케일 점프로만 만들고, 큰 글자일수록 음수 자간을 준다. 전역 `font-feature-settings:"tnum"` — 모든 숫자는 타뷸러.

### Hierarchy
- **Gate** (800, clamp(2.2rem, 6vw, 4.6rem), lh 1.05, -0.02em): 기념비 스케일 핵심 지표 — 남은 kcal, D-숫자, 목표 현재→목표값. 화면당 1–2회.
- **Headline** (800, 1.55rem, -0.015em): 페이지 h1.
- **Title** (800, 1.08rem, -0.01em): 섹션 h2 — 픽토그램·more 링크와 flex 정렬.
- **Value** (800, 1.5rem, -0.01em): 보드 셀 숫자(.val). 단위는 0.7rem/600/뮤트로 축소해 뒤에 붙인다.
- **Body** (400, 1rem, lh 1.6): 본문. 콘텐츠 박스는 0.93rem/lh 1.7.
- **Label** (600, 0.78rem): 데이터 라벨·메타. 뮤트 색. 대문자 변환·자간 벌림 없음.

### Named Rules
**The Weight-Only Hierarchy Rule.** 강조는 굵기 800, 보조는 600+뮤트 색. 이탤릭·대문자·밑줄(링크 hover 제외)로 위계를 만들지 않는다.

**The Shrunken Unit Rule.** 숫자 옆 단위는 항상 본체의 절반 이하 크기(0.68–0.78rem, 600, 뮤트 색)로 숫자에 밀착시킨다. 숫자가 주인공, 단위는 각주.

## Layout

단일 컬럼 흐름. 컨테이너 최대 1020px 중앙 정렬, 패딩 28px 16px 64px. 표면 블록은 세로로 쌓이며 리듬은 margin-bottom 14px(표면 간), 내부 그리드 gap 10px. 다중 지표는 `repeat(auto-fit, minmax(140–190px, 1fr))` 그리드로 자동 랩. 블랙 보드 셀은 `grid-auto-flow:column` 균등 분할 + 1px 패널 라인 구분.

네비게이션은 상단 고정(sticky) 제트블랙 바(min-height 56px) — 공항 천장 안내판. 모바일(≤640px)에서는 가로 스크롤 + 우측 페이드 마스크로 전환하고, 보드는 2컬럼 그리드로 재배열, gate 스케일은 clamp(1.9rem, 9vw, 2.6rem)로 축소.

## Elevation & Depth

그림자를 쓰지 않는다. 깊이는 전적으로 재질 대비로 표현한다: 콘크리트 그라운드 위에 화이트 시트(1px #D9D9D2 보더), 시트 안에는 한 단계 가라앉은 인셋(#F4F4F0, 보더 없음), 블랙 보드는 보더 없이 색 자체가 깊이다. 보드 내부의 상승면은 #242422.

### Named Rules
**The No-Shadow Rule.** box-shadow는 시스템에 존재하지 않는다. 표면을 띄우고 싶으면 재질(배경색)을 바꾼다.

## Shapes

이완된 직사각형 언어. 외곽 표면(사인밴드·보드·시트) 10px, 내부 요소(인셋·버튼·입력·픽토그램 타일) 7px, 칩·배지 5px, 프로그레스 트랙·미니 바 4px — 바깥에서 안으로 갈수록 라운드가 줄어드는 중첩 규칙. 완전 원형(pill)·원은 쓰지 않는다. 픽토그램 타일(.picto)은 38px 정사각(내부 아이콘 22px), 네비 마크는 32px, 로그인 마크는 52px.

### Named Rules
**The Nested Radius Rule.** 컨테이너 10px > 내부 7px > 칩 5px > 트랙 4px. 안쪽 요소가 바깥보다 둥글어지지 않는다.

## Components

### Navigation (천장 안내판)
- 제트블랙 sticky 바, 링크는 온패널 뮤트 600 → hover 시 화이트 → 활성 시 스키폴 옐로 배경 + 제트블랙 텍스트 800 (경로 prefix 매칭 JS).
- 로고: 옐로 32px 타일 + 바벨 픽토그램 + 800 워드마크.
- 모바일: 가로 스크롤, 스크롤 여지가 있으면 우측 26px 페이드 마스크(.can-scroll-right).

### Signband (옐로 안내 밴드)
- 시스템의 시그니처. 옐로 배경 10px 라운드, 제트블랙 텍스트, 좌측 흑색 픽토그램 타일(.picto.on-yellow — 흑색 타일 안 옐로 아이콘), 보조 텍스트는 옐로 잉크(#665000).
- 링크일 때 우측 모서리 고정 화살표(34px), hover 시 배경 #E9B800 + 화살표 translateX(4px).
- 목표·웨이파인딩 콘텐츠 전용. 일반 콘텐츠에 쓰지 않는다.

### Board (제트블랙 데이터 보드)
- 흑색 10px 라운드, 패딩 0 — 셀(.cell, 16px 18px)이 직접 채우고 1px #3A3A37 라인으로 분리.
- 셀 구조: 라벨(0.78rem/600/온패널 뮤트) 위, 값(1.5rem/800) 아래, 단위 축소 첨부.
- 핵심 셀 하나는 gate 스케일 + 옐로(정상) 또는 #FF7A6B(초과)로 승격.
- 보드 위 트랙: 배경 #242422, 필은 옐로.

### Sheet / Inset
- 화이트 시트: 1px #D9D9D2 보더, 10px, 패딩 20px. 일반 콘텐츠·매크로·플랜.
- 인셋: #F4F4F0, 7px, 12px 14px — 시트 안 지표 타일·강조 문단. 보더 없음.

### Buttons
- **Primary:** 제트블랙 배경, 화이트 700 텍스트, 7px, 9px 20px → hover #242422.
- 옐로 버튼은 존재하지 않는다(옐로는 안내 표면이지 액션 색이 아님).

### Inputs
- 화이트 배경, 1px #D9D9D2 보더, 7px, 9px 12px → focus 시 `outline: 2px solid #0E0E0D` (offset -1px). 글로우·색 전환 없음.

### Chips / Badges
- 카테고리 칩: 제트블랙 배경, 화이트 700 텍스트, 5px (미분류 #5D5D57).
- kcal 칩: 시맨틱 틴트 배경 + 시맨틱 텍스트 (low 녹 / mid 앰버 / high 적).
- 배지(트레이너): 옐로 배경 + 제트블랙 700.

### Progress Track
- 8px 높이 4px 라운드 트랙. 밝은 표면: #F4F4F0 트랙 + 흑색 필, 달성 시 .ok(녹) / 초과·미달 시 .bad(적). 보드 위: #242422 트랙 + 옐로 필.

### Pictograms (SVG 스프라이트)
- base.html 인라인 `<defs>` 스프라이트 15종(화살표 좌/우, 바벨, 식사, 인바디, 불꽃, 캘린더, 걷기, 체크, 경고, 타깃, 유저, 차트, 핀). `<use href="#i-*">` + currentColor 단색.
- 인라인 아이콘(.pic)은 1em, 타일 아이콘(.picto)은 38px 흑색 타일 안 22px 화이트.

### Tables (table.rows)
- 0.86rem, 숫자 컬럼 우측 정렬(첫 컬럼만 좌측), 헤더 600 뮤트, 행 구분 1px #D9D9D2 상단 보더만. 세로선·줄무늬 없음. 넓은 표는 `overflow-x:auto` 래퍼.

### Motion
- **Settle 입장:** `.settle` — 표면이 -10px 위에서 0.5s cubic-bezier(.16,1,.3,1)로 내려앉음, 형제 간 0.06s 스태거. `prefers-reduced-motion` 게이트 필수.
- **화살표:** hover 시 translateX(4px), 0.25s 동일 이지.
- **hover 배경:** 0.15s. 스케일·회전·바운스 없음 — 사인은 흔들리지 않는다.

## Do's and Don'ts

### Do:
- **Do** 화면을 세 표면(옐로 밴드 / 블랙 보드 / 화이트 시트)으로 구성하고 콘크리트(#EDEDE9) 위에 놓는다.
- **Do** 핵심 지표 하나를 gate 스케일(clamp 2.2–4.6rem, 800)로 승격하고 나머지는 .val(1.5rem)로 둔다.
- **Do** 이동 가능한 표면 끝에 모서리 고정 화살표 픽토그램을 붙인다.
- **Do** 블랙 보드 위 시맨틱은 밝힌 변형(#7BD8A0 / #FF7A6B)을 쓴다.
- **Do** 새 아이콘이 필요하면 base.html 스프라이트에 24×24 단색 심볼로 추가하고 currentColor로 칠한다.

### Don't:
- **Don't** 옐로를 목표·안내 외 용도(버튼, 상태, 장식, 차트 색)에 쓰지 않는다.
- **Don't** box-shadow·그라디언트·글로우를 쓰지 않는다 — 다크 네온 피트니스 문법 전면 거부.
- **Don't** 카테고리에 컬러 코딩을 하지 않는다 — 칩은 흑색 단일(CATEGORY_COLORS 전부 #0E0E0D).
- **Don't** 컬러 아이콘·이모지 아이콘을 쓰지 않는다 — 픽토그램은 흑백 단색 SVG만.
- **Don't** pill 라운드·원형 컨테이너를 쓰지 않는다 — 최대 라운드는 10px.
