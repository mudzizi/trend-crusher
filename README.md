# TrendCrusher V3: Crypto Trend Following Bot

TrendCrusher는 가상자산 선물 시장을 위한 자동 매매 봇입니다. 변동성 돌파와 적응형 트레일링 스탑을 결합하여 대세 상승장에서의 수익을 극대화하고, 횡보장에서는 손실을 철저히 방어합니다.

## 🚀 주요 특징 (V4 핵심)

- **Multi-Symbol Portfolio Manager (V4 New)**: 여러 코인을 동시에 감시하고, 중앙 매니저가 가용한 자산을 지능적으로 배분 (TRUMP, ETH, SOL 등).
- **Risk-Margin Balancing**: 각 코인별 가중치(Weight)와 리스크(2%)를 동시에 고려하여 최적의 포지션 사이즈 산출.
- **Exposure Control**: 최대 동시 진입 개수(Max Concurrent Trades)를 제한하여 계좌의 총 리스크(Total Risk)를 철저히 관리.
- **ADX Filter**: 추세 강도가 일정 수준 이상일 때만 진입하여 가짜 돌파 필터링.
- **Adaptive Trailing Stop**: 수익률 10%, 20% 돌파 시마다 트레일링 거리를 타이트하게 좁혀 수익 보존.
- **Server-side SL Sync**: 진입 즉시 거래소(Binance) 서버에 손절 주문을 전송하여 봇 장애 시에도 자산 보호.
- **Precision Backtesting**: 1분봉 데이터 기반의 Intra-bar 정밀 검증 완료 (1년치 데이터).
- **Telegram Notification**: 진입, 익절, 손절 및 실시간 상태 알림 제공.

## 📊 최신 검증 성과 (365일)

- **TRUMP/USDT**: 수익률 **+210%** | MDD 17%
- **XAU/USDT**: 수익률 **+186%** | MDD **12%**
- **ETH/USDT**: 수익률 **+161%** | MDD 19%

## 🛠 설치 및 실행

### 1. 환경 설정
`.env.example` 파일을 복사하여 `.env`를 생성하고 API 키를 입력하세요.

```bash
cp .env.example .env
# API_KEY, SECRET, TELEGRAM_TOKEN 등 입력
```

### 2. 가상환경 구축 및 라이브러리 설치
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 멀티 심볼 라이브 봇 실행 (추천)
```bash
# 여러 코인을 동시에 감시하며 자본을 배분하는 통합 봇 실행
PYTHONPATH=. python3 scripts/live_bot_multi.py
```

### 4. 단일 코인 라이브 봇 실행 (Legacy)
```bash
PYTHONPATH=. python3 scripts/live_bot.py
```

### 5. 백테스트 및 최적화
```bash
PYTHONPATH=. python3 scripts/backtest_multi.py    # 멀티 심볼 검증
PYTHONPATH=. python3 backtest/parameter_optimizer.py # 파라미터 최적화
```

## 📂 프로젝트 구조

- **src/portfolio_manager.py**: 중앙 집중식 자본 배분 및 리스크 관리 엔진 (V4 핵심)
- **src/**: 핵심 전략, 지표, 리스크 관리 모듈
- **scripts/**: 라이브 봇 실행 및 백테스트 스크립트
- **backtest/**: 파라미터 최적화 엔진
- **data/**: 백테스트용 OHLCV 데이터 (CSV)
- **tests/**: 로직 검증을 위한 유닛 테스트

---
*Disclaimer: 본 봇은 기술적 분석에 기반한 도구일 뿐이며, 모든 투자 결과의 책임은 투자자 본인에게 있습니다.*
