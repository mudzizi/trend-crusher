# 📊 TrendCrusher V11.6.0: Backtesting Guide

이 가이드는 프로젝트에 포함된 다양한 백테스팅 스크립트의 목적, 차이점 및 결과 해석 방법을 상세히 설명합니다. 최신 업데이트를 통해 모든 백테스팅 스크립트는 라이브 거래 봇(`live_bot_async.py`)과 동일한 **`TrendCrusherV2`** 전략 엔진을 공유하며, 이는 백테스트 결과와 실전 매매 사이의 로직 괴리(Divergence)를 제거합니다.

---

## 🚀 핵심 업데이트: 전략 엔진 동기화 (Single Source of Truth)

기존의 파편화된 백테스트 로직이 `src/strategy.py`의 `TrendCrusherV2` 클래스로 단일화되었습니다.
- **공통 엔진**: `calculate_indicators`, `check_entry_signal`, `check_exit_signal` 메서드가 백테스트와 라이브 봇에서 동일하게 호출됩니다.
- **정밀 시뮬레이션**: `run_precision_backtest` 메서드는 1시간봉 신호와 1분봉 데이터(체크용)를 사용하여 슬리피지, 수수료, 인트라-바 손절을 정확하게 계산합니다.

---

## 1. 📂 스크립트 요약 (Quick Summary)

| 파일명 | 유형 | 주요 목적 | 엔진 |
| :--- | :--- | :--- | :--- |
| `backtest/precision_backtester.py` | 표준 | 가장 정확한 1분 단위 정밀 백테스트 실행 | `TrendCrusherV2` |
| `scripts/mega_optimizer_v2.py` | 최적화 | 병렬 프로세싱을 이용한 다중 종목/파라미터 최적화 | `TrendCrusherV2` |
| `backtest/parameter_optimizer.py` | 탐색 | 특정 종목에 대한 그리드 서치(Grid Search) 최적화 | `TrendCrusherV2` |
| `backtest/sniper_backtester.py` | 비교 | **스나이퍼(지정가)** vs 시장가 진입의 알파(Alpha) 분석 | `TrendCrusherV2` (Ext) |
| `scripts/backtest_portfolio.py` | 포트폴리오 | 종목별 비중을 고려한 전체 자산 합산 수익률 계산 | `TrendCrusherV2` |

---

## 2. 📝 스크립트별 상세 분석

### 🏗️ Standard: `backtest/precision_backtester.py`
리팩토링된 전략 엔진의 성능을 확인하는 표준 스크립트입니다.
- **특징:** 1시간봉(신호) + 4시간봉(추세) + 1분봉(검증) 데이터를 모두 사용하여 실전에 가장 가까운 결과를 냅니다.
- **실행법:** `python3 backtest/precision_backtester.py`

### 🧠 Optimizer: `scripts/mega_optimizer_v2.py` (권장)
바이낸스 상위 종목들에 대해 최적의 파라미터 세트를 찾아줍니다.
- **특징:** 
    - `ProcessPoolExecutor`를 사용한 병렬 최적화로 속도가 매우 빠릅니다.
    - Market, Sniper, Retest_Maker 세 가지 모드를 모두 시뮬레이션하여 가장 효율적인 모드를 제안합니다.
- **결과 지표:** `Efficiency` (수익률 / MDD). 이 수치가 높을수록 안정적인 설정입니다.
- **실행법:** `python3 scripts/mega_optimizer_v2.py [종목개수] [기간(일)]`

### 🎯 Advanced: `backtest/sniper_backtester.py`
TrendCrusher의 핵심인 **'스나이퍼 엔진'**의 가치를 정량화합니다.
- **특징:** 
    - 돌파 시점의 가격 움직임을 1분 단위로 분석하여 지정가 체결 가능성을 판별합니다.
    - 체결 성공 시 **지정가 수수료(0.02%) 및 제로 슬리피지**를 적용하여 시장가 진입 대비 추가 수익(Alpha)을 계산합니다.
- **실행법:** `python3 backtest/sniper_backtester.py`

### 💼 Portfolio: `scripts/backtest_portfolio.py`
여러 종목에 자산 배분을 했을 때의 통합 성과를 보여줍니다.
- **특징:** 개별 종목의 변동성이 상쇄되는 '분산 투자 효과'를 MDD 수치로 확인할 수 있습니다.
- **실행법:** `python3 scripts/backtest_portfolio.py`

---

## 3. 📊 결과 해석 및 실전 적용

1. **로직 일관성 확인**: 
   백테스트 결과가 좋다면, 해당 파라미터를 `config.yaml`의 `SYMBOL_SETTINGS`에 적용하세요. 라이브 봇은 백테스트와 **정확히 동일한 코드**로 진입과 청산을 결정합니다.

2. **MDD (최대 낙폭) 기준**:
   실전 운영을 위해서는 MDD가 15~20% 이하인 설정을 권장합니다. MDD가 너무 높다면 `RISK_PER_TRADE`를 낮추거나 `ADX_FILTER_LEVEL`을 높이십시오.

3. **거래 횟수와 신뢰도**:
   테스트 기간 동안 거래 횟수가 너무 적으면 통계적 유의성이 떨어집니다. 최소 30회 이상의 거래가 발생한 설정을 신뢰하세요.

---

## 🛠️ 백테스팅 실행 시 주의사항
- **데이터 필수**: `data/` 폴더에 `{SYMBOL}_1h.csv`, `4h.csv`, `1m.csv`가 모두 존재해야 합니다. (부족할 경우 `BinanceDataFetcher`를 통해 다운로드됩니다.)
- **수수료 및 슬리피지**: `TrendCrusherV2`는 기본적으로 시장가 0.05%, 지정가 0.02%의 수수료를 적용합니다. 보수적인 결과를 위해 `config.yaml`에서 슬리피지를 조절할 수 있습니다.

---
**TrendCrusher Development Team**
*Your Technical Co-Founder for Algo-Trading*
