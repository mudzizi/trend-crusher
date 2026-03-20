# 🚀 TrendCrusher V11: The Phoenix Engine
> **"시장을 추격하지 말고, 길목에서 매복하라. 쓰러져도 다시 일어나라."**
> 
> TrendCrusher는 초저지연 비동기 알고리즘과 철저한 회복력을 결합한 가상자산 선물 매매 시스템입니다. V11.0.1 버전에서는 **The Sniper**의 정밀함과 함께, 봇이 죽어도 스스로 되살아나는 **Phoenix Watchdog** 체계를 완성했습니다.

---

## 🚀 주요 특징 (v11.0.1 핵심)

- **Resilience Watchdog (v11.0.1 New)**: 봇 프로세스를 실시간 감시하고 OOM Killer나 크래시 발생 시 즉시 알림 후 자동 재시작.
- **Last Will & Testament (v11.0.1 New)**: 봇 사망 직전 에러 원인이나 종료 신호를 텔레그램으로 즉시 보고하는 자가 진단 기능.
- **The Precision Sniper**: 돌파 직전에 Maker 지정가로 매복하여 슬리피지 제로 및 수수료 절감 달성.
- **The Sentinel (v10)**: 매주 정기 스캔 및 성과 하락 시 긴급 재최적화를 제안하는 지능형 파수꾼.
- **WebSocket Async Engine**: 밀리초(ms) 단위의 반응 속도로 시장의 모든 틱(Tick) 데이터 실시간 처리.
- **Smart Isolated Margin**: 한 종목의 리스크가 계좌 전체를 위협하지 않도록 철저한 자산 격리 매매 수행.

---

## 📊 Sniper Mode 검증 성과 (1년 / 실전 압박 테스트)
*가혹한 조건(슬리피지 0.5%) 하에서의 시장가 대비 수익 향상폭*

| 종목 | 일반 시장가 모드 | **스나이퍼 모드 (Limit)** | **Alpha (수익 향상)** | 성공률 |
| :--- | :---: | :---: | :---: | :---: |
| **TRUMP/USDT** | +83.89% | **+835.82%** | **+751%** | 40.0% |
| **ETH/USDT** | +39.69% | **+676.17%** | **+636%** | 35.4% |
| **XAU/USDT** | -13.93% | **+343.27%** | **+357%** | 71.4% |

---

## 📱 Telegram 원격 지휘 및 운영 가이드

| 명령어 | 설명 | 비고 |
| :--- | :--- | :--- |
| `/status` | 모든 코인의 포지션, 수익률, 매복 상태 보고 | 실시간 PnL 확인 |
| `/optimize [SYM]` | 해당 코인의 최적 파라미터 재계산 지시 | 자가 학습 트리거 |
| `/apply [SYM]` | 제안된 파라미터를 실전에 즉시 반영 | Hot-Reload |
| `/sniper_on/off` | 선제적 지정가 매복 모드 활성/비활성 제어 | 저격 모드 스위치 |
| `/stop` / `/resume` | 신규 진입 로직 중단 및 재개 | 운영 통제 |
| `/close_all` | **[긴급 킬 스위치]** 전 포지션 즉시 종료 및 봇 중단 | 비상 사태용 |

---

## 🛠 설치 및 실행

### 1. 연결 확인 (추천)
```bash
PYTHONPATH=. python3 scripts/test_telegram_commands.py
```

### 2. 라이브 봇 실행 (권장: Watchdog 사용)
운영 안정성을 위해 워치독을 통해 봇을 실행하는 것을 강력히 권장합니다.
```bash
# 봇을 감시하고 자동으로 되살리는 워치독 엔진 가동
PYTHONPATH=. python3 scripts/watchdog.py
```

### 3. 스나이퍼 성능 검증 (백테스트)
```bash
PYTHONPATH=. python3 backtest/sniper_backtester.py
```

## 📂 프로젝트 구조
- `scripts/watchdog.py`: **The Lifeline.** 봇을 감시하고 자동 재시작을 수행.
- `scripts/live_bot_async.py`: **Main Engine.** 지능형 비동기 웹소켓 통합 매매 엔진.
- `src/portfolio_manager_async.py`: 비동기 안전 자본 및 격리 마진 관리자.
- `src/optimizer_engine.py`: Walk-Forward 분석 기반 자가 학습 엔진.
- `src/db_manager.py`: 0.1초 단위 상태 복구를 위한 데이터 영속화 엔진.

---
*Disclaimer: 본 소프트웨어는 기술적 분석 도구이며, 가상자산 투자에는 원금 손실의 위험이 따릅니다. 모든 투자의 책임은 사용자 본인에게 있습니다.*
