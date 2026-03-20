# TrendCrusher V8: Remote Command & Control Bot

TrendCrusher는 가상자산 선물 시장을 위한 인텔리전트 자동 매매 엔진입니다. V8 버전에서는 **Command & Control(C&C)** 시스템을 도입하여 스마트폰 하나로 언제 어디서나 봇을 지휘하고 비상 시 즉시 통제할 수 있는 원격 지휘 체계를 완성했습니다.

## 🚀 주요 특징 (V8 핵심)

- **Remote Command & Control (v8.0.0 New)**: 텔레그램을 통한 양방향 명령 체계. `/status`, `/stop`, `/resume`, `/close_all` 명령어로 원격 지휘 가능.
- **Hourly Heartbeat Reporting (v8.0.0 New)**: 1시간마다 봇의 생존 여부와 포트폴리오 요약을 자동으로 보고.
- **WebSocket Async Engine**: 시장의 틱(Tick) 발생 즉시 반응하는 비동기 엔진으로 슬리피지 최소화.
- **Atomic Order Safety**: 진입-손절 배치를 하나의 원자적 단위로 관리. 손절 배치 실패 시 즉시 자동 청산.
- **Smart Isolated Margin**: 신규 진입 시 자동으로 격리 마진(Isolated)을 설정하여 타 종목 리스크 전이 차단.
- **Independent Capital Isolation**: 코인별 독립 가상 장부 관리로 철저한 자본 격리 실현.

## 📊 최신 검증 성과 (365일 / S-Tier)

- **TRUMP/USDT**: 수익률 **+210.07%** | MDD 17.29%
- **XAU/USDT**: 수익률 **+186.89%** | MDD **12.55%**
- **ETH/USDT**: 수익률 **+161.44%** | MDD 19.80%

## 🛠 텔레그램 원격 명령어

- `/status`: 현재 모든 코인의 포지션 상태 및 수익률 요약 보고.
- `/stop`: 새로운 진입(Entry)만 중단 (기존 포지션은 계속 추적).
- `/resume`: 중단된 진입 로직 재가동.
- `/close_all`: **[긴급 킬 스위치]** 모든 포지션 즉시 시장가 종료 및 봇 중단.

## 🛠 설치 및 실행

### 1. 라이브 봇 실행 (V8 비동기 엔진)
```bash
# 초저지연 틱 데이터 기반 원격 제어 통합 봇 실행
PYTHONPATH=. python3 scripts/live_bot_async.py
```

### 2. 실시간 포트폴리오 대시보드
```bash
# 브라우저에서 http://localhost:5000 접속
PYTHONPATH=. python3 scripts/dashboard.py
```

## 📂 프로젝트 구조

- **scripts/live_bot_async.py**: 원격 지휘가 가능한 비동기 웹소켓 통합 매매 엔진 (V8 핵심)
- **src/telegram_utils.py**: 양방향 통신 및 리포팅 모듈
- **src/portfolio_manager_async.py**: 비동기 안전 자본 관리자
- **tests/**: 27개의 검증된 Unit/Integration 테스트

---
*Disclaimer: 본 소프트웨어는 기술적 분석 도구이며, 모든 투자의 책임은 사용자 본인에게 있습니다.*
