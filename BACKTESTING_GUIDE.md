# 📊 TrendCrusher V11.6.0: Backtesting Guide

이 가이드는 프로젝트에 포함된 다양한 백테스팅 스크립트의 목적, 차이점 및 결과 해석 방법을 상세히 설명합니다. TrendCrusher는 단순한 수익률 계산을 넘어, 실전 매매에서 발생할 수 있는 슬리피지, 수수료 리베이트, 인트라-바 변동성을 정밀하게 시뮬레이션합니다.

---

## 1. 📂 스크립트 요약 (Quick Summary)

| 파일명 | 유형 | 주요 목적 | 데이터 소스 |
| :--- | :--- | :--- | :--- |
| `scripts/backtest_multi.py` | 표준 | 여러 종목의 수익률과 MDD 일괄 확인 | 1h, 4h, 1m |
| `scripts/backtest_portfolio.py` | 포트폴리오 | 종목별 비중을 고려한 전체 자산 합산 수익률 계산 | 1h, 4h, 1m |
| `backtest/sniper_backtester.py` | 심화 | **스나이퍼 모드(지정가)** vs 일반 모드 수익성 비교 | 1h, 4h, 1m |
| `backtest/precision_backtester.py` | 정밀 | 1분 단위 데이터로 손절/익절 로직의 정확도 검증 | 1h, 4h, 1m |
| `scripts/mega_optimizer.py` | 최적화 | 바이낸스 거래량 상위 20개 종목의 최적 파라미터 탐색 | 실시간 API + CSV |
| `backtest/compounding_tester.py` | 분석 | 복리(Compounding)와 단리 매매의 수익 격차 분석 | 1h, 4h, 1m |

---

## 2. 📝 스크립트별 상세 분석

### 🚀 Standard: `scripts/backtest_multi.py`
가장 기본이 되는 백테스터입니다. `config.yaml`에 등록된 `SYMBOLS_LIST`의 모든 종목을 순차적으로 테스트합니다.
-   **특징:** 각 종목별 `SYMBOL_SETTINGS`를 자동으로 반영합니다.
-   **결과 지표:** 
    -   `Return(%)`: 기간 내 총 수익률.
    -   `MDD(%)`: 최대 자산 하락폭.
    -   `Trades`: 총 거래 횟수.
-   **실행법:** `PYTHONPATH=. python3 scripts/backtest_multi.py`

### 🎯 Advanced: `backtest/sniper_backtester.py` (중요)
TrendCrusher의 핵심인 **'스나이퍼 엔진'**의 경제적 가치를 증명합니다.
-   **특징:** 
    -   시가와 돌파 가격의 거리를 계산하여 '매복 성공(Limit)'과 '추격 실패(Market)'를 구분합니다.
    -   매복 성공 시 **제로 슬리피지 + 지정가 수수료(0.02%)**를 적용합니다.
    -   실패 시 **0.5% 슬리피지 + 시장가 수수료(0.04%)**를 적용하여 시장가 대비 우위를 정량화합니다.
-   **실행법:** `PYTHONPATH=. python3 backtest/sniper_backtester.py`

### 🏗️ Strategy: `backtest/precision_backtester.py`
1시간봉 신호를 기준으로 하되, 청산 판단은 1분봉으로 진행하는 정밀 시뮬레이터입니다.
-   **특징:** 캔들이 닫히기 전에 터지는 손절(SL)이나 트레일링 스탑을 1분 단위로 추적하여, 1시간봉 종가 기준 백테스트의 오류(오버피팅)를 방지합니다.
-   **결과 해석:** 이 테스트의 MDD가 실제 운영 시 겪게 될 리스크에 가장 가깝습니다.
-   **실행법:** `PYTHONPATH=. python3 backtest/precision_backtester.py`

### 💼 Portfolio: `scripts/backtest_portfolio.py`
전체 자본금을 여러 종목에 분산 투자했을 때의 결과를 보여줍니다.
-   **특징:** `Weight`(비중)를 설정하여 자산 배분 효과를 확인합니다. (예: TRUMP 40%, ETH 30%, XAU 30%)
-   **인사이트:** 개별 종목의 MDD보다 합산 포트폴리오의 MDD가 낮아지는 **'분산 효과'**를 시각화합니다.
-   **실행법:** `PYTHONPATH=. python3 scripts/backtest_portfolio.py`

### 🧠 Optimizer: `scripts/mega_optimizer.py`
바이낸스에서 잘 먹히는 종목과 그에 맞는 파라미터를 찾아줍니다.
-   **특징:** 거래량 상위 20개 종목에 대해 `Vol_Multiplier`, `ADX_Level`, `EMA_Period` 등을 그리드 서치(Grid Search)합니다.
-   **결과 지표:** `Efficiency` (수익률 / MDD). 이 수치가 높을수록 적은 리스크로 큰 수익을 낸 최적의 설정입니다.
-   **실행법:** `PYTHONPATH=. python3 scripts/mega_optimizer.py [제한개수]`

---

## 3. 📊 결과 해석 가이드 (How to Read Results)

1.  **Alpha (알파) 수치:**
    -   스나이퍼 모드 백테스트에서 `Market Ret`과 `Sniper Ret`의 차이를 보세요.
    -   이 차이가 클수록 해당 종목은 변동성이 커서 지정가 매복의 효과가 극대화되는 종목입니다.

2.  **MDD (Max Drawdown) 관리:**
    -   MDD가 20%를 초과한다면 리스크가 높다는 신호입니다. `RISK_PER_TRADE`를 낮추거나 `ADX_FILTER_LEVEL`을 높여 진입 기준을 깐깐하게 조정해야 합니다.

3.  **Trades (거래 횟수):**
    -   1년 기준 거래 횟수가 너무 적다면(10회 미만) 통계적으로 신뢰하기 어렵습니다.
    -   너무 많다면(300회 이상) 수수료가 수익을 갉아먹을 수 있으므로 `VOL_MULTIPLIER`를 높여야 합니다.

---

## 🛠️ 백테스팅 실행 시 주의사항
-   **데이터 유무:** `data/` 폴더에 `{SYMBOL}_1h.csv`, `4h.csv`, `1m.csv` 파일이 있어야 합니다. 없으면 `scripts/backtest_multi.py`가 자동으로 다운로드합니다.
-   **슬리피지 설정:** 보수적인 테스트를 위해 `config.yaml`의 `SLIPPAGE`를 `0.005`(0.5%) 정도로 높여서 테스트하는 것을 권장합니다.

---
**TrendCrusher Development Team**
*Your Technical Co-Founder for Algo-Trading*
