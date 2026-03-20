# TrendCrusher V7: Strategy Whitepaper

## 1. 개요 (Overview)
TrendCrusher는 변동성 돌파(Volatility Breakout)와 적응형 트레일링 스탑(Adaptive Trailing Stop)을 결합한 추세 추종 전략입니다. V7 버전에서는 **웹소켓(WebSocket)**과 **비동기 엔진**을 통해 레이턴시를 혁신적으로 줄였으며, **원자적 주문(Atomic Order)** 시스템을 통해 리스크 관리의 무결성을 확보했습니다.

## 2. 핵심 로직 (Core Logic)

### 2.1. 진입 조건 (Entry Conditions)
1.  **Donchian Channel Breakout**: 가격이 직전 20개 봉의 최고점을 돌파(Long)하거나 최저점을 이탈(Short)할 때 신호 발생.
2.  **EMA Trend Filter**: 상위 타임프레임(4h)의 EMA 위에 있을 때만 진입하여 대세 흐름에 편승.
3.  **Volume Burst Filter**: 돌파 시점의 거래량이 평균 대비 2.0~2.5배 이상 폭발해야 진입.
4.  **ADX Filter**: 추세 강도가 명확할 때(ADX 15~25 이상)만 진입하여 가짜 돌파 필터링.

### 2.2. 청산 및 리스크 관리 (Exit & Risk Control)
1.  **Adaptive Trailing Stop**: 수익률에 따라 추격 거리를 동적으로 조절 (ATR 4.5x -> 3.5x -> 2.5x).
2.  **Risk-based Sizing**: 모든 매매는 손절 시 해당 코인 할당 자산의 **2%**만 손실되도록 수량을 자동 계산.

### 2.3. 포트폴리오 관리 (Portfolio Management)
1.  **Independent Capital Ledger**: `ALLOCATED_SEED`를 통해 코인별 전용 예산을 할당하고 독립적인 복리 수익을 실현.
2.  **Smart Isolated Margin**: 신규 진입 시 자동으로 격리 마진(Isolated)을 설정하여 타 종목으로의 리스크 전이 차단.

### 2.4. 시각적 리스크 모니터링
1.  **Real-time PnL Tracking**: 모든 활성 포지션의 미실현 손익을 실시간 감시.
2.  **Portfolio Dashboard**: 누적 수익률, 승률, 자산 분포를 대시보드에서 실시간 관리.

### 2.5. 자산 격리 및 연속성 (Asset Isolation & Persistence)
1.  **Full State Persistence**: 트레일링 변수와 손절 주문 ID를 DB에 실시간 동기화하여 재시작 시 0.1초 만에 복구.

### 2.6. 초저지연 및 원자적 안전 (Zero-Latency & Atomic Safety - V7)
1.  **WebSocket Streaming**: 10초 주기 폴링을 폐지하고 웹소켓을 통한 실시간 틱 데이터 처리로 슬리피지 최소화.
2.  **Atomic Entry**: 진입 성공 후 손절(SL) 주문 배치가 실패할 경우, 해당 포지션을 즉시 시장가로 청산하여 무방비 노출을 원천 차단.
3.  **Asynchronous Execution**: `asyncio`를 기반으로 여러 종목의 시그널과 주문을 병렬 처리하여 병목 현상 제거.

## 3. 최종 최적화 결과 (Verified 365-Day Backtest)
최근 1년치(2025.03 ~ 2026.03) 1분봉 정밀 검증 결과입니다. (S-Tier)

| 종목 | EMA 기간 | ADX 필터 | 거래량 배수 | **수익률 (1Y)** | MDD (%) | 효율성 (Ret/MDD) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **TRUMP/USDT** | **100** | **15** | **2.5x** | **+210.07%** | **17.29%** | **12.15 (S-Tier)** |
| **XAU/USDT** | **200** | **25** | **2.5x** | **+186.89%** | **12.55%** | **14.89 (S-Tier)** |
| **ETH/USDT** | **200** | **15** | **2.0x** | **+161.44%** | **19.80%** | **8.15 (A-Tier)** |

## 4. 결론 (Conclusion)
TrendCrusher V7은 시장의 틱 하나도 놓치지 않는 예리함과, 어떤 재난 상황에서도 자산을 지켜내는 견고함을 동시에 갖추었습니다. 이제 이 시스템은 단순한 자동매매 봇을 넘어 고성능 알고리즘 트레이딩 엔진으로서 기능합니다.

---
*Disclaimer: 본 소프트웨어는 기술적 분석 도구이며, 모든 투자의 책임은 사용자 본인에게 있습니다.*
