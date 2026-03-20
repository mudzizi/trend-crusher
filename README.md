# 🚀 TrendCrusher V11: The Precision Sniper
> **"시장을 추격하지 말고, 길목에서 매복하라."**
> 
> TrendCrusher는 가상자산 선물 시장의 변동성을 정밀하게 포착하여 수익으로 치환하는 **초저지연 비동기 알고리즘 매매 시스템**입니다. 단순한 지표 추종을 넘어, 시장의 틱(Tick) 데이터를 실시간 분석하고 최적의 타점에 지정가(Maker)로 매복하는 독보적인 '스나이퍼' 기술을 탑재하고 있습니다.

---

## 📑 목차 (Table of Contents)
1. [시스템 철학](#-시스템-철학)
2. [핵심 전략 (The 4 Pillars)](#-핵심-전략-the-4-pillars)
3. [기술적 도약 (V11 Engine)](#-기술적-도약-v11-engine)
4. [운영 가이드 (Operations)](#-운영-가이드-operations)
5. [성과 지표 (Performance)](#-성과-지표-performance)
6. [설치 및 실행 (Setup)](#-설치-및-실행-setup)
7. [프로젝트 구조 (Structure)](#-프로젝트-구조-structure)

---

## 🎯 시스템 철학
대부분의 자동매매 봇은 돌파가 일어난 **후**에 시장가로 따라붙습니다. 이는 슬리피지와 높은 수수료라는 독배를 마시는 행위입니다. TrendCrusher V11은 돌파의 전조 현상을 감지하여 **정확한 돌파 가격에 미리 지정가(Limit)를 배치**합니다. 우리는 시장의 'Taker'가 아닌 'Maker'로서, 수수료를 아끼고 가장 유리한 평단가를 선점합니다.

---

## 🧠 핵심 전략 (The 4 Pillars)
모든 진입은 다음 4가지 조건이 완벽하게 일치할 때만 실행됩니다 (The 4-Pillars Guard).

1.  **Donchian Channel Breakout**: 가격이 직전 고점/저점을 돌파하는 찰나의 모멘텀 포착.
2.  **Volume Burst Filter**: 거래량이 평균 대비 **2.0~2.5배 이상** 폭발하며 에너지가 응축될 때만 진입.
3.  **ADX Trend Strength**: ADX(14) 지표를 통해 힘없는 박스권 돌파를 걸러내고 강력한 추세에만 탑승.
4.  **EMA Macro Filter**: 4시간봉 대이평선을 통해 시장의 큰 흐름(장기 추세)과 일치하는 방향으로만 배팅.

---

## 🛡️ 기술적 도약 (V11 Engine)

### 1. WebSocket Async Engine
10초 주기 폴링(Polling)의 시대를 끝냈습니다. 바이낸스 선물 웹소켓 스트림을 통해 시장의 모든 숨결(Tick)을 실시간으로 수신하며, 밀리초(ms) 단위로 대응합니다.

### 2. The Precision Sniper (v11 New)
가격이 돌파 레벨에 0.5% 이내로 접근하고 4대 기둥 조건이 충족되면 즉시 **지정가 매복 주문**을 실행합니다. 조건이 단 하나라도 틀어지면 0.1초 만에 주문을 취소하여 가짜 돌파(Fakeout)를 방어합니다.

### 3. The Sentinel (v10 Self-Learning)
봇이 스스로 시장을 공부합니다. 매주 최근 30일 데이터를 학습하여 최적의 파라미터(변동성 배수, 이평선 등)를 도출하고 주인님께 제안서를 발송합니다.

### 4. Atomic Order Safety
진입과 손절(Stop-Loss) 주문을 하나의 원자적 단위로 관리합니다. 손절 주문 배치가 실패할 경우, 시스템은 자산을 보호하기 위해 잡았던 포지션을 즉시 시장가로 청산합니다.

---

## 📱 운영 가이드 (Operations)

### 텔레그램 원격 지휘 본부
스마트폰 하나로 전 세계 어디서나 봇을 완벽하게 통제할 수 있습니다.

| 명령어 | 설명 | 비고 |
| :--- | :--- | :--- |
| `/status` | 모든 코인의 포지션, 수익률, 매복 상태 보고 | 실시간 PnL 확인 |
| `/optimize [SYM]` | 해당 코인의 최적 파라미터 재계산 지시 | 자가 학습 트리거 |
| `/apply [SYM]` | 봇이 제안한 최적 파라미터를 실전에 즉시 반영 | Hot-Reload |
| `/sniper_on/off` | 선제적 지정가 매복 모드 활성/비활성 제어 | 킬 스위치 1 |
| `/stop` / `/resume` | 신규 진입 로직 중단 및 재개 | 운영 통제 |
| `/close_all` | **[긴급 킬 스위치]** 전 포지션 즉시 종료 및 봇 중단 | 비상 사태용 |

---

## 📊 성과 지표 (Performance)
*가혹한 시장 조건(슬리피지 0.5%) 하에서의 1년 누적 백테스트 결과*

| 종목 | 일반 시장가 모드 | **스나이퍼 모드 (Limit)** | **Alpha (수익 향상)** |
| :--- | :---: | :---: | :---: |
| **TRUMP/USDT** | +83.89% | **+835.82%** | **+751%** |
| **ETH/USDT** | +39.69% | **+676.17%** | **+636%** |
| **XAU/USDT** | -13.93% | **+343.27%** | **+357%** |

---

## 🛠 설치 및 실행

### 1. 연결 확인 (Connection Check)
봇 가동 전, 텔레그램 명령과 보안 설정이 정상인지 반드시 확인하세요.
```bash
PYTHONPATH=. python3 scripts/test_telegram_commands.py
```

### 2. 라이브 봇 실행 (Live Trading)
```bash
# V11 지능형 비동기 웹소켓 엔진 가동
PYTHONPATH=. python3 scripts/live_bot_async.py
```

### 3. 리포트 확인 (Backtest Reports)
수행된 백테스트 결과는 다음 구조로 자동 저장됩니다.
`reports/[SYM]/[Mode]/[Time]/report.png`

---

## 📂 프로젝트 구조
- `scripts/live_bot_async.py`: **Main Engine.** 비동기 웹소켓 통합 매매 오케스트레이터.
- `src/portfolio_manager_async.py`: 코인별 독립 자본 및 격리 마진 관리자.
- `src/optimizer_engine.py`: Walk-Forward 분석 기반 자가 학습 엔진.
- `src/db_manager.py`: 0.1초 단위 상태 복구를 위한 데이터 영속화 엔진.
- `backtest/sniper_backtester.py`: 스나이퍼 경제 효과 정밀 시뮬레이터.
- `tests/`: 34개의 엄격한 유닛 및 통합 테스트 케이스.

---
*Disclaimer: 본 소프트웨어는 기술적 분석 도구이며, 가상자산 투자에는 원금 손실의 위험이 따릅니다. 모든 투자의 책임은 사용자 본인에게 있습니다.*
