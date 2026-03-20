# TrendCrusher V11: The Precision Sniper

TrendCrusher는 가상자산 선물 시장을 위한 인텔리전트 자동 매매 시스템입니다. V11 버전에서는 **The Sniper (선제적 지정가 매복 시스템)**를 도입하여, 돌파가 일어나는 정확한 찰나에 Maker 수수료를 받으며 슬리피지 없이 진입하는 완벽한 타점 알고리즘을 완성했습니다.

## 🚀 주요 특징 (V11 핵심)

- **The Precision Sniper (v11.0.0 New)**: 시장가 추격을 버리고, 돌파 직전(99.5%)에 4대 기둥(Volume, ADX, EMA)이 일치할 때만 전고점에 지정가(Maker)로 매복하는 선제 진입 시스템.
- **Slippage Elimination**: 고변동성 장세에서도 지정가 매복을 통해 슬리피지를 0%로 수렴시킴.
- **The Sentinel (v10)**: 매주 정기 스캔 및 성과 하락 시 긴급 재최적화를 수행하는 지능형 파수꾼.
- **WebSocket Async Engine**: 밀리초(ms) 단위의 반응 속도로 틱 데이터 실시간 처리.
- **Atomic Order Safety**: 진입-손절 배치를 하나의 원자적 단위로 관리.

## 📊 Sniper Mode 검증 성과 (1년 / 실전 압박 테스트)
*가혹한 조건(슬리피지 0.5%) 하에서의 시장가 대비 수익 향상폭*

| 종목 | 일반 시장가 모드 | **스나이퍼 모드 (Limit)** | **수익 향상 (Alpha)** |
| :--- | :---: | :---: | :---: |
| **TRUMP/USDT** | +83.89% | **+835.82%** | **+751%** |
| **ETH/USDT** | +39.69% | **+676.17%** | **+636%** |
| **XAU/USDT** | -13.93% | **+343.27%** | **+357%** |

---

## 📱 Telegram 원격 지휘 및 운영 가이드

TrendCrusher V11은 텔레그램을 통해 전 세계 어디서나 봇을 지휘할 수 있는 강력한 인터페이스를 제공합니다.

### 1. 기본 모니터링
*   **/status**: 모든 코인의 포지션 상태, 수익률, 스나이퍼 매복 상태(🎯 AMBUSHING) 보고.
*   **Hourly Heartbeat**: 매 1시간마다 봇이 포트폴리오 요약을 자동으로 전송.

### 2. 지능형 최적화 (The Sentinel)
*   **/optimize [SYMBOL]**: 최근 데이터를 기반으로 파라미터 재계산 지시.
*   **/apply [SYMBOL]**: 제안된 파라미터를 즉시 실전에 적용(Hot-Reload).

### 3. 긴급 통제 및 스나이퍼 제어
*   **/sniper_off**: 스나이퍼 모드를 끄고 즉시 시장가 진입 모드로 전환.
*   **/sniper_on**: 선제적 지정가 매복(Maker) 모드 활성화.
*   **/close_all**: **[긴급 킬 스위치]** 전 포지션 종료 및 봇 중단.

---

## 🛠 설치 및 실행

### 1. 연결 확인 (추천)
```bash
PYTHONPATH=. python3 scripts/test_telegram_commands.py
```

### 2. 라이브 봇 실행
```bash
PYTHONPATH=. python3 scripts/live_bot_async.py
```

### 3. 스나이퍼 성능 검증 (백테스트)
```bash
PYTHONPATH=. python3 backtest/sniper_backtester.py
```

## 📂 프로젝트 구조

- **backtest/sniper_backtester.py**: 스나이퍼 경제 효과 정밀 시뮬레이터 (V11 핵심)
- **scripts/live_bot_async.py**: 지능형 비동기 웹소켓 통합 매매 엔진
- **src/optimizer_engine.py**: 자가 적응형 파라미터 최적화 엔진
- **tests/**: 34개의 검증된 Unit/Integration 테스트 케이스

---
*Disclaimer: 본 소프트웨어는 기술적 분석 도구이며, 모든 투자의 책임은 사용자 본인에게 있습니다.*
