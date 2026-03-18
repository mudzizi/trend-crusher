# 🚀 TrendCrusher: High-Performance Crypto Trend Follower

**TrendCrusher**는 바이낸스 선물(USDT-M) 시장에서 변동성과 추세를 동시에 추적하는 전문 자동 매매 시스템입니다. 시장의 폭발적인 돌파(Breakout) 순간을 포착하고, 정밀한 리스크 관리 알고리즘을 통해 자산을 보호하며 수익을 극대화합니다.

---

## 💡 매매 전략 (Core Strategy)

본 시스템은 다음의 하이브리드 전략을 사용합니다:
- **Trend Filter (4H)**: 100일 EMA를 통해 장기 추세 방향(BULL/BEAR)을 확인합니다.
- **Volatility Breakout (1H)**: 20일 Donchian Channel의 상단/하단을 강하게 돌파할 때 진입합니다.
- **Volume Burst**: 평균 거래량 대비 설정값 이상의 거래량이 터졌을 때만 신호로 인정하여 가짜 돌파(Fakeout)를 필터링합니다.
- **Exit Strategy**: ATR(Average True Range) 기반의 초기 손절선과 수익 발생 시 작동하는 **Dynamic Trailing Stop**을 결합하여 이익을 보존합니다.

---

## 📂 프로젝트 구조 (Project Structure)

```text
TrendCrusher/
├── src/                # 핵심 로직 및 유틸리티
│   ├── config.py       # 모든 설정 및 파라미터
│   ├── strategy.py     # 백테스트 및 매매 전략 엔진
│   ├── indicators.py   # 기술적 지표 계산 (Donchian, ATR, EMA 등)
│   └── ...             # DB, Telegram, Visualizer 등
├── backtest/           # 전략 검증 및 최적화 도구
│   ├── backtester.py   # 다중 심볼 성능 테스트
│   └── parameter_optimizer.py # 그리드 서치 최적화 엔진
├── scripts/            # 실행 가능한 엔트리 포인트
│   ├── live_bot.py     # 실전 매매/드라이런 봇
│   ├── dashboard.py    # Flask 기반 실시간 모니터링 웹
│   └── main.py         # 단일 백테스트 실행 스크립트
├── data/               # 수집된 시장 데이터 (CSV)
├── log/                # 봇 구동 상세 로그
└── reports/            # 생성된 매매 차트 리포트 (PNG)
```

---

## 🛠 1. 설치 및 설정 (Setup)

### 설치
```bash
# Python 3.10 이상 권장
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### `src/config.py` 설정
1. **API Keys**: 바이낸스 API(`Futures` 권한 필요) 및 텔레그램 봇 토큰 입력.
2. **Operational**: `DRY_RUN` 여부, `SYMBOL`, `SEED`(운용 자금) 설정.
3. **Safety**: `MAX_LEVERAGE`를 통해 증거금 부족 및 과도한 베팅 방지.

---

## 🚀 2. 운용 워크플로우 (Workflow)

### Step 1: 데이터 수집
매매하려는 코인의 과거 데이터를 수집합니다.
```bash
export PYTHONPATH=$PYTHONPATH:.
python src/data_fetcher.py
```

### Step 2: 전략 최적화 및 백테스트
가장 높은 효율(Profit/MDD)을 보이는 파라미터를 찾습니다.
```bash
python backtest/parameter_optimizer.py
```

### Step 3: 실전 매매 시작 (PM2 사용 권장)
서버에서 백그라운드로 봇을 안정적으로 가동합니다.
```bash
pm2 start scripts/live_bot.py --name "TrendCrusher" --interpreter ./venv/bin/python
```

### Step 4: 실시간 모니터링
웹 브라우저를 통해 현재 상태와 매매 기록을 확인합니다.
```bash
python scripts/dashboard.py
```
- 접속: `http://your-server-ip:5000`

---

## 🛡 3. 안전 장치 (Safety Features)

- **Risk-based Sizing**: 매 회 손절 시 원금의 2%(`RISK_PER_TRADE`)만 손실되도록 수량을 자동 계산합니다.
- **Leverage Cap**: 변동성이 낮을 때 수량이 무한정 늘어나는 것을 방지하기 위해 최대 레버리지를 제한합니다.
- **Margin Check**: 바이낸스 API 규칙에 맞춘 수량 정밀도 및 최소 주문 단위 체크 로직 탑재.
- **Real-time Alert**: 모든 진입/청산/오류 상황을 텔레그램으로 즉시 알림.

---

## ⚠️ 면책 조항 (Disclaimer)
본 소프트웨어는 투자 참고용이며, 실제 매매로 인한 손실은 사용자 본인에게 책임이 있습니다. 반드시 **DRY_RUN(가상 매매)** 모드에서 충분한 테스트를 거친 후 실전에 투입하십시오.
