# TrendCrusher V13.3.8: Strategy Whitepaper (V7.0 Chaos Engine)

## 1. 개요 (Overview)
TrendCrusher는 변동성 돌파(Volatility Breakout)와 모멘텀 카오스(Momentum Chaos)를 결합한 초정밀 추세 추종 전략입니다. v13.3.8 버전은 **'V7.0 Chaos & Squeeze 엔진'**을 탑재하여 시장의 광기(Mania/Panic)를 수익으로 전환하며, 최적화된 API 통신 구조로 실전 운영의 안정성을 극대화했습니다.

## 2. 핵심 로직 (Core Logic)

### 2.1. 진입 조건 (Entry Conditions)
진입 신호는 **1시간봉(1h) 기준의 기술적 지표**를 바탕으로 하되, **웹소켓 실시간 데이터**를 결합하여 캔들 중간에도 즉각 대응합니다.
1.  **Donchian Channel Breakout**: 가격이 직전 N개 봉의 최고점을 돌파(Long)하거나 최저점을 이탈(Short)할 때 포착.
2.  **Chaos Index Filter (V7.0)**: 단순 추세 강도가 아닌, 시장의 불균형이 극에 달한 '카오스' 구간을 감지. 에너지 폭발 직전의 신호만 선별.
3.  **Volatility Squeeze Score**: 볼린저 밴드가 켈트너 채널 내부로 수렴(Squeeze)하여 에너지가 압축된 상태에서 터지는 브레이크아웃을 가점 요소로 활용.
4.  **EMA Slope & MTF Filter**: 상위 타임프레임(4h) ADX와 현재 EMA의 기울기(Slope)를 통해 거시적 추세 방향과 진입의 가속도를 동시에 검증.
5.  **Asymmetric Short Bias**: 하락장의 공포(Fear)가 상승장의 탐욕(Greed)보다 빠르다는 원리에 따라, 숏 진입 시 거래량과 ADX 문턱값을 30~40% 낮게 설정하여 기민하게 대응.

### 2.2. 신호 안정성 및 히스테리시스 (Signal Stability)
이미 주문이 나간 대기 상태(`Ambushing`)에서 사소한 지표 흔들림으로 인해 주문이 취소되는 것을 방지합니다.
-   **Filter Hysteresis (20%)**: 거래량과 ADX가 기준치의 80% 수준까지만 유지되어도 대기 주문 유지.
-   **Intelligent Sync**: 웹소켓 데이터로 메모리상에서 실시간 지표를 업데이트하되, 캔들 확정 시에만 REST API로 데이터 무결성을 최종 검증.

### 2.3. 청산 및 리스크 관리 (Exit & Risk Control)
1.  **Adaptive Trailing Stop**: 수익률 단계에 따라 ATR 기반 손절 배수를 동적으로 좁혀 이익을 보존.
2.  **Break-even Guard**: 수익률이 설정값(예: 3%)을 넘어서는 순간, 손절가를 즉시 진입가 위로 이동하여 원금을 100% 보호.
3.  **Risk-based Sizing**: 모든 매매는 손절 시 총 자산의 일정 비율(예: 2%)만 손실되도록 수량을 자동 계산.

### 2.4. 운영 리질리언스 (Operational Resilience)
1.  **Nuclear SL Cleanup**: 새로운 손절 주문 생성 전 거래소의 모든 기존 주문을 강제 취소하여 중복 주문 발생을 물리적으로 차단.
2.  **SSOT(Single Source of Truth)**: 봇 시작 시 거래소의 실제 포지션 상태를 1순위로 동기화하여 데이터 인지 부조화 해결.
3.  **Self-Healing Connection**: ListenKey 만료 및 웹소켓 단절 시 자동으로 세션을 재구축하고 주문 상태를 재검토.

## 3. 정밀 검증 성과 (Hyper-Sim Results)
Look-ahead Bias가 완벽히 제거된 2년(730일) 통합 시뮬레이션 결과입니다. (v13.3.8 엔진 기준)

| 종목 | 최종 수익률 | 최대 낙폭 (MDD) | 효율 (Ret/MDD) | 특징 |
| :--- | :---: | :---: | :---: | :--- |
| **TRUMP/USDT** | **+139.55%** | 27.81% | 5.00 | 하락장 속 강력한 우상향 |
| **BTC/USDT** | **+42.12%** | 15.30% | 2.75 | 메이저 자산 안정성 확보 |
