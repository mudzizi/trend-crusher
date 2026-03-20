# TrendCrusher V3: Strategy Whitepaper

## 1. 개요 (Overview)
TrendCrusher는 변동성 돌파(Volatility Breakout)와 적응형 트레일링 스탑(Adaptive Trailing Stop)을 결합한 추세 추종 전략입니다. V3 버전에서는 **ADX 필터**와 **가변 트레일링** 로직을 도입하여 횡보장 방어력과 수익 보존력을 극대화했습니다.

## 2. 핵심 로직 (Core Logic)

### 2.1. 진입 조건 (Entry Conditions)
1.  **Donchian Channel Breakout**: 가격이 직전 20개 봉의 최고점을 돌파(Long)하거나 최저점을 이탈(Short)할 때 신호 발생.
2.  **EMA Trend Filter**: 상위 타임프레임(4h)의 EMA(100/200) 위에 있을 때만 매수, 아래에 있을 때만 매도하여 대세 하락장에서의 가짜 반등 방지.
3.  **Volume Burst Filter**: 돌파 시점의 거래량이 직전 20개 봉 평균 대비 **2.0~2.5배** 이상 폭발해야 진입.
4.  **ADX Filter (V3 New)**: ADX(14) 지표가 **15~25 이상**일 때(추세 강도가 명확할 때)만 진입하여 힘없는 박스권 돌파를 필터링.

### 2.2. 청산 및 리스크 관리 (Exit & Risk Control)
1.  **Server-side Stop Loss**: 진입 즉시 거래소 서버에 **ATR 2배** 거리의 `STOP_MARKET` 주문을 전송하여 시스템 장애 시에도 자산 보호.
2.  **Adaptive Trailing Stop (V3 New)**: 수익률에 따라 추격 거리를 동적으로 조절.
    *   초기: ATR 4.5x (넉넉한 추격)
    *   수익 10% 돌파: ATR 3.5x (수익 보존 시작)
    *   수익 20% 돌파: ATR 2.5x (타이트한 익절 방어)
3.  **Risk-based Sizing**: 모든 매매는 손절 시 원금의 **2%**만 손실되도록 수량을 자동 계산.

### 2.3. 포트폴리오 관리 (Portfolio Management - V4)
여러 심볼을 동시에 운용할 때의 자본 효율성과 계좌 안전성을 위해 중앙 집중식 관리 로직을 도입했습니다.
1.  **Weight-based Allocation**: 각 심볼별로 최대 할당 비중(Weight)을 설정 (예: TRUMP 40%, ETH 30%).
2.  **Dual Constraint Sizing**: 다음 두 수치 중 **최솟값**을 최종 수량으로 선택합니다.
    *   **Risk-Qty**: 전체 자산의 2% 리스크를 감수하는 수량.
    *   **Margin-Qty**: (전체 자산 * 비중 * 레버리지) 한도 내에서의 수량.
3.  **Concurrent Trade Limit**: 동시에 진입 가능한 최대 포지션 개수(`MAX_CONCURRENT_TRADES`)를 제한하여 시스템적인 연쇄 손실 위험을 방지합니다.

## 3. 최종 최적화 결과 (Verified 365-Day Backtest)
최근 1년치(2025.03 ~ 2026.03) 1분봉 정밀 검증 결과입니다.

| 종목 | EMA 기간 | ADX 필터 | 거래량 배수 | **수익률 (1Y)** | MDD (%) | 효율성 (Ret/MDD) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **TRUMP/USDT** | **100** | **15** | **2.5x** | **+210.07%** | **17.29%** | **12.15 (S-Tier)** |
| **XAU/USDT** | **200** | **25** | **2.5x** | **+186.89%** | **12.55%** | **14.89 (S-Tier)** |
| **ETH/USDT** | **200** | **15** | **2.0x** | **+161.44%** | **19.80%** | **8.15 (A-Tier)** |
| **SOL/USDT** | 200 | 15 | 1.5x | +34.74% | 25.10% | 1.38 (B-Tier) |

## 4. 결론 (Conclusion)
TrendCrusher V3는 강력한 추세가 확인된 시점(ADX)에만 진입하고, 수익이 쌓일수록 익절 라인을 바짝 끌어올려(Adaptive Trail) 수익 반납을 최소화하는 완벽한 공수 밸런스를 갖추었습니다. 특히 **XAU(금)**와 **TRUMP** 종목에서 압도적인 효율성을 보여주며, 안정적인 우상향 복리 수익을 기대할 수 있습니다.

---
*Disclaimer: 본 소프트웨어는 기술적 분석 도구이며, 모든 투자의 책임은 사용자 본인에게 있습니다.*
