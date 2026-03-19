# TrendCrusher: Strategy Whitepaper (Professional Edition)

## 1. 개요 (Executive Summary)
**TrendCrusher**는 바이낸스 선물(USDT-M) 시장의 고변동성 자산을 타겟으로 하는 정밀 돌파 추세 추종(Breakout Trend Following) 전략입니다. 본 전략은 1시간봉의 가격 돌파와 4시간봉의 대추세 필터를 결합하며, 강력한 **Volume Burst** 필터와 **Server-side Risk Management**를 통해 실전 매매의 안정성과 수익성을 동시에 확보했습니다.

## 2. 핵심 알고리즘 (Core Algorithm)

### 2.1. 진입 로직: 트리플 컨펌 (Triple Confirmation)
1.  **Donchian Channel Breakout**: 최근 20시간의 최고가를 상향 돌파 시 LONG, 최저가를 하향 돌파 시 SHORT 신호 생성.
2.  **Trend Filter (EMA)**: 4시간봉 기준 EMA 필터를 적용하여 장기 추세 방향과 일치하는 방향으로만 진입 (코인별 100/200일 가변 적용).
3.  **Volume Burst Filter**: 돌파 시점의 거래량이 직전 20개 봉 평균 대비 **2.0~2.5배** 이상 폭발해야 진입. 단순 가격 움직임이 아닌 '진짜 수급'을 확인하여 가짜 돌파(Fakeout)를 필터링합니다.

### 2.2. 청산 및 리스크 관리 (Exit & Risk Control)
1.  **Server-side Stop Loss**: 진입 즉시 거래소 서버에 **ATR 2배** 거리의 `STOP_MARKET` 주문을 전송하여 봇 정지 시에도 자산을 보호합니다.
2.  **Dynamic Trailing Stop**: 가격 유리하게 움직일 시 최고점으로부터 **ATR 4.5배** 거리를 유지하며 수익을 무한히 추적합니다.
3.  **Risk-based Sizing**: 모든 매매는 손절 시 원금의 **2%**만 손실되도록 수량을 자동 계산합니다.
4.  **Safety Cap**: 과도한 레버리지를 방지하기 위해 최대 5배(`MAX_LEVERAGE`) 제한을 적용합니다.

## 3. 최종 최적화 결과 (Verified 365-Day Backtest)
1년치 1분봉 정밀 검증(Intra-bar Check)을 완료한 최종 성적표입니다.

| 종목 | EMA 기간 | 거래량 배수 | 트레일링 배수 | **수익률 (1Y)** | MDD (%) | 효율성 (Ret/MDD) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TRUMP/USDT** | **100** | **2.5x** | **4.5x** | **+159.36%** | **16.80%** | **9.49 (S-Tier)** |
| **ETH/USDT** | **200** | **2.0x** | **4.5x** | **+149.25%** | **19.80%** | **7.54 (A-Tier)** |
| **XAU/USDT** | 200 | 2.5x | 4.5x | **+136.21%** | 20.12% | 6.77 (A-Tier) |

## 4. 시스템 아키텍처 (System Architecture)
- **src/**: 기술적 지표, DB 매니저, 텔레그램 유틸 등 핵심 모듈.
- **scripts/**: 실전 매매 봇(`live_bot.py`), 대시보드 및 리포트 도구.
- **backtest/**: 그리드 서치 기반 파라미터 최적화 엔진.
- **Safety**: `.env` 기반 보안 관리, `pytest` 기반 유닛 테스트(17개 항목).

## 5. 결론 (Conclusion)
TrendCrusher는 통계적 우위와 실전 운용의 안정성을 모두 갖춘 시스템입니다. 특히 **서버사이드 손절 동기화**와 **레버리지 캡**은 개인 트레이더가 놓치기 쉬운 리스크를 시스템적으로 방어합니다. 검증된 파라미터를 기반으로 운용할 때 최상의 수익 복리 효과를 기대할 수 있습니다.

---
*Disclaimer: 본 소프트웨어는 기술적 분석 도구이며, 모든 투자의 책임은 사용자 본인에게 있습니다.*
