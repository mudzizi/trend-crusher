# 📊 TrendCrusher V11.8.0: The Ultimate Backtesting Guide

이 가이드는 TrendCrusher의 업계 최고 수준 정밀 백테스팅 엔진과 시뮬레이션 도구들의 목적, 차이점 및 결과 해석 방법을 상세히 설명합니다. v11.8.0은 **Look-ahead Bias(미래 참조 오류)**를 원천 차단한 실전형 엔진을 제공합니다.

---

## 🚀 핵심 기술: 스트리밍 시뮬레이션 (Streaming Simulation)

기존 백테스트의 가장 큰 약점은 1시간봉이 마감된 후의 지표를 사용하여 그 시간대 내부의 진입을 결정하는 '미래 참조'였습니다. TrendCrusher v11.8.0은 이를 혁신적으로 해결했습니다.

### 1. 단일 진실 공급원 (Single Source of Truth)
- **공통 엔진**: `src/strategy.py`의 `TrendCrusherV2`가 라이브 거래와 모든 백테스트의 유일한 판단 기준입니다.
- **로직 완벽 일치**: `check_entry_signal`과 `check_exit_signal` 메서드가 실전 매매와 백테스트에서 100% 동일하게 실행됩니다.

### 2. 제로 바이어스 (No Look-ahead Bias)
- **분 단위 지표 재구성**: `run_streaming_backtest` 메서드는 1분봉 데이터를 스트리밍하듯 읽으며, 매 분마다 **'현재까지 진행된 미완성 1시간봉'**을 기반으로 지표를 계산합니다.
- **현실적인 거래량 판단**: 1시간이 끝나기 전, 실제로 거래량이 터지는 찰나의 순간을 포착하여 진입 타이밍을 시뮬레이션합니다.

---

## 📂 스크립트 요약 (Simulation Suite)

| 파일명 | 유형 | 주요 목적 | 엔진 모드 |
| :--- | :--- | :--- | :--- |
| `scripts/run_realistic_simulation.py` | **최고 정밀** | ** Look-ahead Bias 0%** 초정밀 스트리밍 시뮬레이션 | `Streaming` |
| `backtest/precision_backtester.py` | 표준 | 인트라-바 검증을 포함한 빠른 정밀 백테스트 | `Precision` |
| `scripts/mega_optimizer_v2.py` | 최적화 | 다중 종목에 대한 고속 파라미터 그리드 서치 | `Precision` |
| `backtest/sniper_backtester.py` | 분석 | 지정가 매복(Sniper)의 수수료 절감 효과 분석 | `Precision` |

---

## 📝 주요 도구 상세 가이드

### 🏗️ Ultra-Realistic: `scripts/run_realistic_simulation.py`
가장 권장되는 최종 검증 도구입니다. 
- **특징:** 1분 단위 스트리밍 업데이트를 시뮬레이션하여 실전과 가장 유사한 수익률을 산출합니다.
- **결과물:** 
    - `reports/{SYMBOL}/{MODE}/{TIMESTAMP}/` 경로에 구조화된 저장.
    - **Visual Chart**: 지표, 거래 시점, 자산 곡선이 통합된 4단 패널 PNG.
    - **Trade Log**: 모든 진입/청산의 상세 내역 CSV.
- **실행:** `python3 scripts/run_realistic_simulation.py`

### 🧠 Hyper-Optimizer: `scripts/mega_optimizer_v2.py`
수백 개의 파라미터 조합 중 수익/리스크 비율이 가장 좋은 최적값을 찾아줍니다.
- **지표:** `Return/MDD Efficiency`가 가장 높은 조합을 우선 제안합니다.
- **실행:** `python3 scripts/mega_optimizer_v2.py [종목수] [기간]`

---

## 📊 결과 해석 및 시각화 (Visualization)

v11.8.0은 데이터 수치를 넘어 시각적인 직관을 제공합니다.

1.  **종합 시각 리포트 (Visual Chart)**:
    - **Price Panel**: 진입(▲/▼)과 청산(X) 지점을 가격 차트 위에 지표와 함께 표시.
    - **ADX/Volume Panel**: 진입 당시의 추세 강도와 거래량 폭발 여부 검증.
    - **Equity Panel**: 리스크 5% 등의 복리 효과가 자산 곡선에 미치는 영향 확인.

2.  **대시보드 통합**:
    - `python3 scripts/dashboard.py` 실행 후 웹 브라우저에서 모든 백테스트 이미지와 CSV를 즉시 확인 및 다운로드 가능.

---

## 🛠️ 백테스팅 실행 시 주의사항

- **증분 데이터 업데이트**: `BinanceDataFetcher`는 이제 기존 데이터가 있다면 마지막 시점 이후의 데이터만 추가로 가져옵니다. 업데이트 속도가 매우 빠릅니다.
- **현실적인 비용 설정**: 
    - **Sniper/Market**: Taker 수수료(0.05%) + 현실적인 슬리피지 적용.
    - **Retest Maker**: **Maker 수수료(0.02%)** + 제로 슬리피지 적용.
- **리스크 경고**: 백테스트에서 MDD가 20%를 넘는다면 실전에서는 더 큰 심리적 고통이 따를 수 있습니다. `RISK_PER_TRADE`를 조절하여 본인에게 맞는 설정을 찾으세요.

---
**TrendCrusher Development Team**
*The Gold Standard in Realistic Trading Simulation*
