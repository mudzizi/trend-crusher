# TrendCrusher V9: Self-Adaptive Intelligence Bot

TrendCrusher는 가상자산 선물 시장을 위한 자가 진화형 자동 매매 엔진입니다. V9 버전에서는 **Walk-Forward 최적화 엔진**을 도입하여 시장의 성격 변화를 스스로 학습하고, 매 순간 가장 효율적인 파라미터를 찾아내는 인공지능형 시스템을 완성했습니다.

## 🚀 주요 특징 (V9 핵심)

- **Self-Adaptive Intelligence (v9.0.0 New)**: 최근 30일 데이터를 학습하여 최적의 파라미터를 스스로 도출하는 자가 적응형 엔진.
- **Remote Optimization Control (v9.0.0 New)**: 텔레그램 `/optimize` 명령어로 실시간 파라미터 튜닝 및 Hot-Reload 지원.
- **Efficiency-based Selection**: 단순히 수익률만 보는 것이 아니라 `Return / MDD` 효율이 가장 높은 조합을 선발.
- **Remote Command & Control**: 스마트폰을 통한 전 방향 원격 지휘 및 긴급 킬 스위치 운영.
- **WebSocket Async Engine**: 초저지연 비동기 엔진으로 시장의 모든 틱(Tick)에 즉각 반응.
- **Atomic Order Safety**: 진입-손절 배치를 하나의 원자적 단위로 묶어 무방비 노출 원천 차단.

## 📊 최신 검증 성과 (365일 / S-Tier)

- **TRUMP/USDT**: 수익률 **+210.07%** | MDD 17.29%
- **XAU/USDT**: 수익률 **+186.89%** | MDD **12.55%**
- **ETH/USDT**: 수익률 **+161.44%** | MDD 19.80%

## 🛠 텔레그램 원격 명령어

- `/status`: 현재 모든 코인의 포지션 상태 및 수익률 보고.
- `/optimize [SYMBOL]`: 최근 30일 데이터를 기반으로 해당 코인의 **최적 파라미터 재계산 및 즉시 적용**.
- `/stop` / `/resume`: 새로운 진입 로직 제어.
- `/close_all`: **[긴급 킬 스위치]** 전 포지션 즉시 종료 및 봇 중단.

## 🛠 설치 및 실행

### 1. 라이브 봇 실행 (V9 지능형 엔진)
```bash
# 자가 최적화 및 원격 제어 지원 통합 봇 실행
PYTHONPATH=. python3 scripts/live_bot_async.py
```

### 2. 실시간 포트폴리오 대시보드
```bash
# 브라우저에서 http://localhost:5000 접속
PYTHONPATH=. python3 scripts/dashboard.py
```

## 📂 프로젝트 구조

- **src/optimizer_engine.py**: 자가 적응형 파라미터 최적화 엔진 (V9 핵심)
- **scripts/live_bot_async.py**: 지능형 비동기 웹소켓 통합 매매 엔진
- **src/portfolio_manager_async.py**: 비동기 안전 자본 관리자
- **tests/**: 29개의 검증된 Unit/Integration 테스트 (최적화 로직 포함)

---
*Disclaimer: 본 소프트웨어는 기술적 분석 도구이며, 모든 투자의 책임은 사용자 본인에게 있습니다.*
