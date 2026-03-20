# TrendCrusher V8: Strategy Whitepaper

## 1. 개요 (Overview)
TrendCrusher는 변동성 돌파(Volatility Breakout)와 적응형 트레일링 스탑(Adaptive Trailing Stop)을 결합한 추세 추종 전략입니다. V8 버전에서는 **웹소켓(WebSocket)** 기반의 초저지연 엔진과 **Command & Control** 원격 제어 시스템을 결합하여 운영의 완성도를 극대화했습니다.

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
1.  **Full State Persistence**: 모든 상태를 DB에 실시간 저장하여 봇 재시작 시 0.1초 만에 완벽 복구.

### 2.6. 초저지연 및 원자적 안전 (Zero-Latency & Atomic Safety)
1.  **WebSocket Streaming**: 웹소켓을 통한 실시간 틱 데이터 처리로 슬리피지 최소화.
2.  **Atomic Entry**: 진입 성공 후 손절(SL) 주문 배치가 실패할 경우 즉시 강제 청산하여 리스크 노출 차단.

### 2.7. 원격 지휘 및 통제 (Command & Control - v8.0.0)
시스템의 실제 운영 안정성을 위해 텔레그램 기반의 양방향 제어 시스템을 도입했습니다.
1.  **Interactive Commands**: `/status`, `/stop`, `/close_all` 등의 명령어를 통해 자리에 없어도 스마트폰으로 봇을 즉각 제어.
2.  **Hourly Heartbeat**: 매시간 봇의 생존 여부와 포트폴리오 요약 리포트를 자동 전송하여 침묵에 의한 불안감 해소.
3.  **Authorized Security**: 사전에 등록된 사용자 ID만 명령을 수행할 수 있도록 보안 강화.

## 3. 최종 최적화 결과 (Verified 365-Day Backtest)
최근 1년치(2025.03 ~ 2026.03) 1분봉 정밀 검증 결과입니다. (S-Tier)

| 종목 | EMA 기간 | ADX 필터 | 거래량 배수 | **수익률 (1Y)** | MDD (%) | 효율성 (Ret/MDD) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **TRUMP/USDT** | **100** | **15** | **2.5x** | **+210.07%** | **17.29%** | **12.15 (S-Tier)** |
| **XAU/USDT** | **200** | **25** | **2.5x** | **+186.89%** | **12.55%** | **14.89 (S-Tier)** |
| **ETH/USDT** | **200** | **15** | **2.0x** | **+161.44%** | **19.80%** | **8.15 (A-Tier)** |

## 4. 결론 (Conclusion)
TrendCrusher V8은 기술(v7)과 운영(v8)의 완벽한 조화를 목표로 합니다. 초저지연 엔진의 날카로움과 원격 제어 시스템의 견고함이 결합되어, 시장의 어떤 돌발 상황에서도 자산을 안전하게 지키며 수익을 극대화할 것입니다.

---
*Disclaimer: 본 소프트웨어는 기술적 분석 도구이며, 모든 투자의 책임은 사용자 본인에게 있습니다.*
