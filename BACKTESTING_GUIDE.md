# 📊 TrendCrusher V13.3.0: Unified Simulation Suite

TrendCrusher V13.3.0은 복잡하게 흩어져 있던 백테스트 및 최적화 도구들을 단 두 개의 **통합 엔진(Unified Engine)**으로 단일화했습니다. 모든 도구는 **V7.0 Chaos & Squeeze** 로직을 기본 탑재하고 있습니다.

---

## 1. 통합 백테스터: `scripts/backtest.py`

단일 종목 혹은 다수 종목에 대해 고정된 파라미터로 정밀 시뮬레이션을 수행하고 시각화 리포트를 생성합니다.

### 🚀 주요 기능
- **V7.0 엔진**: Chaos Index, Squeeze Score, MTF 필터 기본 적용.
- **자동 데이터 동기화**: 시작 전 바이낸스에서 최신 데이터를 자동으로 가져옵니다.
- **시각화 리포트**: `reports/` 폴더에 차트와 거래 내역을 자동으로 생성합니다.

### 💻 사용법
```bash
# 기본 실행 (ETH/USDT, 최근 365일, Market 모드)
python3 scripts/backtest.py

# 특정 종목 지정 및 기간 설정
python3 scripts/backtest.py --symbol TRUMP/USDT --days 180 --mode sniper

# 다수 종목 동시 테스트
python3 scripts/backtest.py --symbol BTC/USDT,ETH/USDT,SOL/USDT --days 90
```

---

## 2. 통합 최적화 도구: `scripts/optimize.py`

Optuna(베이지안 최적화)를 사용하여 주어진 기간 동안 가장 높은 효율(Return/MDD)을 내는 파라미터 조합을 찾습니다.

### 🚀 주요 기능
- **지능형 탐색**: 단순 그리드 서치가 아닌, 인공지능이 유망한 파라미터 영역을 집중 탐색합니다.
- **V7.0 변수 탐색**: Chaos, Squeeze, Slope 지표의 임계값을 포함하여 최적의 조합을 산출합니다.
- **다중 목적 최적화**: 수익률 극대화와 MDD 최소화를 동시에 고려합니다.

### 💻 사용법
```bash
# 기본 실행 (ETH/USDT, 365일, 100회 탐색)
python3 scripts/optimize.py

# 특정 종목에 대해 정밀 탐색 (500회)
python3 scripts/optimize.py --symbol TRUMP/USDT --trials 500

# 여러 종목의 최적값 순차 탐색
python3 scripts/optimize.py --symbol ETH/USDT,XRP/USDT --days 180
```

---

## 📂 결과 해석 가이드

1.  **Efficiency (효율)**: `Return / (MDD + 0.1)`. 이 수치가 **1.0 이상**이면 매우 우수한 전략이며, **2.0 이상**이면 실전 투입 가치가 매우 높습니다.
2.  **Chaos Index**: 최적화 결과 ADX보다 Chaos Index 문턱값이 높게 잡힌다면, 해당 종목은 '광기' 구간에서 수익이 극대화됨을 의미합니다.
3.  **MDD Guard**: 백테스트 MDD가 25%를 초과할 경우, `RISK_PER_TRADE`를 낮추는 것을 권장합니다.

---

## 🛠️ 레거시 도구 안내
이전 버전의 스크립트들은 `legacy/` 폴더로 이동되었습니다. 특별한 사유가 없다면 위의 통합 도구 사용을 강력히 권장합니다.

---
**TrendCrusher V13.3.0 Development Team**
*The New Standard in Momentum Trading*
