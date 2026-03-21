# TrendCrusher V11: Strategy Whitepaper

## 1. 개요 (Overview)
TrendCrusher는 변동성 돌파(Volatility Breakout)와 적응형 트레일링 스탑(Adaptive Trailing Stop)을 결합한 추세 추종 전략입니다. V11.2.0 버전은 웹소켓 기반의 **실시간 인트라-바(Intra-bar) 감지** 엔진을 통해 지표는 1시간을 보되, 실행은 1초를 앞서가는 초저지연 매매 체계를 완성했습니다.

## 2. 핵심 로직 (Core Logic)

### 2.1. 진입 조건 (Entry Conditions)
진입 신호는 **1시간봉(1h) 기준의 기술적 지표**를 바탕으로 하되, **웹소켓 실시간 데이터(2초 주기)**를 결합하여 캔들 중간에도 즉각 대응합니다.
1.  **Donchian Channel Breakout**: 가격이 직전 20개 봉의 최고점을 돌파(Long)하거나 최저점을 이탈(Short)할 때 신호 발생. 실시간 가격 업데이트를 통해 캔들 종가 대기 없이 즉시 포착.
2.  **EMA Trend Filter**: 상위 타임프레임(4h)의 EMA 위에 있을 때만 진입.
3.  **Volume Burst Filter**: 돌파 시점의 거래량이 평균 대비 2.0~2.5배 이상 폭발해야 진입. 인트라-바 거래량 급증을 실시간으로 감지.
4.  **ADX Filter**: 추세 강도가 명확할 때(ADX 15~25 이상)만 진입.

### 2.2. 청산 및 리스크 관리 (Exit & Risk Control)
1.  **Adaptive Trailing Stop**: 수익률에 따라 추격 거리를 동적으로 조절 (ATR 4.5x -> 3.5x -> 2.5x).
2.  **Risk-based Sizing**: 모든 매매는 손절 시 해당 코인 할당 자산의 **2%**만 손실되도록 수량을 자동 계산.

### 2.3. 포트폴리오 관리 (Portfolio Management)
1.  **Independent Capital Ledger**: `ALLOCATED_SEED`를 통해 코인별 전용 예산을 할당하고 독립적인 복리 수익을 실현.
2.  **Smart Isolated Margin**: 신규 진입 시 자동으로 격리 마진(Isolated)을 설정하여 타 종목으로의 리스크 전이 차단.

### 2.4. 초저지연 및 실시간 엔진 (Real-time Async Engine - v11.1.2)
1.  **WebSocket Intra-bar Updates**: 캔들이 닫힐 때까지 기다리지 않고 실시간 틱 데이터를 OHLCV 버퍼에 즉시 반영하여 지연 시간 제로화.
2.  **Smart Timeframe Filtering**: `1m` 등의 불필요한 데이터 스트림을 필터링하여 연산 효율성 극대화 및 API 오버헤드 방지.
3.  **Atomic Entry**: 진입 성공 후 손절(SL) 주문 배치가 실패할 경우 즉시 강제 청산하여 리스크 노출 차단.

### 2.5. 선제적 지정가 매복 시스템 (The Sniper)
1.  **Zero-Offset Target**: 정확한 돌파 레벨(`Donchian`)에 지정가 주문을 배치하여 Maker 수수료를 확보.
2.  **The 4-Pillars Guard**: 가격, 거래량, 추세, 방향성이 모두 일치할 때만 매복 실행.

### 2.6. 자가 학습형 파수꾼 (The Sentinel)
1.  **Walk-Forward Optimization**: 최근 30일 데이터를 기반으로 최적 파라미터를 도출하여 텔레그램으로 제안.
2.  **Live Hot-Reload**: 봇 중단 없이 실시간으로 최적화된 파라미터를 실전에 투입.

### 2.11. 운영 회복력 및 파수견 시스템 (Operational Resilience - v11.1.1)
시스템의 연속 가동성과 장애 대응력을 프로페셔널 등급으로 강화했습니다.
1.  **Last Will Notification**: 봇 프로세스가 예기치 못한 에러(Crash)나 시스템 신호(SIGTERM)로 종료될 때, 마지막 순간의 상태와 원인을 텔레그램으로 즉시 보고합니다.
2.  **External Watchdog (Phoenix)**: 봇 외부에서 독립적으로 가동되는 감시 스크립트가 프로세스 상태를 1초 단위로 모니터링합니다. OOM Killer 등 침묵 속의 사망 발생 시 즉시 주인님께 알리고 봇을 자동 재시작합니다.
3.  **1-Minute Logging Heartbeat (v11.1.2)**: 매매 신호가 없는 정적 구간에서도 1분마다 현재 가격과 상태를 로그에 남겨 시스템의 건강 상태를 투명하게 공개합니다.

### 2.5. 선제적 지정가 매복 시스템 (The Sniper)
1.  **Zero-Offset Target**: 정확한 돌파 레벨(`Donchian`)에 지정가 주문을 배치하여 Maker 수수료를 확보.
2.  **The 4-Pillars Guard**: 가격, 거래량, 추세, 방향성이 모두 일치할 때만 매복 실행.

### 2.6. 자가 학습형 파수꾼 (The Sentinel)
1.  **Walk-Forward Optimization**: 최근 30일 데이터를 기반으로 최적 파라미터를 도출하여 텔레그램으로 제안.
2.  **Live Hot-Reload**: 봇 중단 없이 실시간으로 최적화된 파라미터를 실전에 투입.

### 2.11. 운영 회복력 및 파수견 시스템 (Operational Resilience - v11.1.1)
시스템의 연속 가동성과 장애 대응력을 프로페셔널 등급으로 강화했습니다.
1.  **Last Will Notification**: 봇 프로세스가 예기치 못한 에러(Crash)나 시스템 신호(SIGTERM)로 종료될 때, 마지막 순간의 상태와 원인을 텔레그램으로 즉시 보고합니다.
2.  **External Watchdog (Phoenix)**: 봇 외부에서 독립적으로 가동되는 감시 스크립트가 프로세스 상태를 1초 단위로 모니터링합니다. OOM Killer 등 침묵 속의 사망 발생 시 즉시 주인님께 알리고 봇을 자동 재시작합니다.
3.  **Safe Resource Release**: 어떤 형태의 종료 상황에서도 거래소 API 세션을 명시적으로 닫아 리소스 누수를 방지합니다.

## 3. Sniper Mode 성능 검증 (Stress Test Results)
시장이 가혹한 상황(슬리피지 0.5%)일 때, 스나이퍼 모드와 일반 시장가 모드의 1년 누적 성과를 비교한 결과입니다.

| 종목 | 시장가 모드 (0.5% Slip) | **스나이퍼 모드 (Maker)** | **수익 향상 (Alpha)** | 성공률 |
| :--- | :---: | :---: | :---: | :---: |
| **TRUMP/USDT** | +83.89% | **+835.82%** | **+751.93%** | 40.0% |
| **ETH/USDT** | +39.69% | **+676.17%** | **+636.48%** | 35.4% |
| **XAU/USDT** | -13.93% | **+343.27%** | **+357.20%** | 71.4% |

## 4. 결론 (Conclusion)
TrendCrusher V11.1.1은 **"기술적 예리함"**과 **"운영적 견고함"**의 완벽한 결합체입니다. 스나이퍼의 날카로운 타점으로 수익을 극대화하고, 워치독의 끈질긴 생명력으로 시스템의 중단 없는 성장을 보장합니다.

---
*Disclaimer: 본 소프트웨어는 기술적 분석 도구이며, 모든 투자의 책임은 사용자 본인에게 있습니다.*
