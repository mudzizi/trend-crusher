# TrendCrusher V7: Zero-Latency WebSocket Async Bot

TrendCrusher는 가상자산 선물 시장을 위한 초고속 자동 매매 시스템입니다. V7 버전에서는 **WebSocket 스트리밍**과 **비동기(Asyncio)** 엔진을 도입하여 지연 시간을 밀리초(ms) 단위로 단축하고, 어떤 상황에서도 자산을 보호하는 **Atomic Order** 안전 시스템을 구축했습니다.

## 🚀 주요 특징 (V7 핵심)

- **WebSocket Async Engine (V7 New)**: 10초 주기 폴링이 아닌, 시장의 틱(Tick) 발생 즉시 반응하는 비동기 엔진. 슬리피지를 혁명적으로 감소.
- **Atomic Order Safety (V7 New)**: 진입과 손절(SL) 배치를 하나의 원자적 단위로 관리. SL 배치 실패 시 즉시 포지션을 강제 청산하여 무방비 노출 차단.
- **Fault-Tolerant Error Handling (V7 New)**: 네트워크 장애 시 지수적 백오프 재시도 및 치명적 에러 시 긴급 탈출(Panic Exit) 로직 적용.
- **Smart Isolated Margin**: 포지션이 없는 코인 진입 시 자동으로 격리 마진(Isolated)을 설정하여 리스크 전이 차단.
- **Independent Capital Isolation**: 코인별 `ALLOCATED_SEED` 기반의 가상 장부 관리. 독립적 복리 수익 실현.
- **Real-time Portfolio Dashboard**: 전체 자산 현황과 실시간 PnL을 시각적으로 모니터링.

## 📊 최신 검증 성과 (365일 / S-Tier)

- **TRUMP/USDT**: 수익률 **+210.07%** | MDD 17.29%
- **XAU/USDT**: 수익률 **+186.89%** | MDD **12.55%**
- **ETH/USDT**: 수익률 **+161.44%** | MDD 19.80%

## 🛠 설치 및 실행

### 1. 환경 설정
`.env` 파일에 API 키와 텔레그램 정보를 입력하세요.

### 2. 가상환경 및 설치
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 라이브 봇 실행 (V7 비동기 웹소켓 엔진 - 추천)
```bash
# 초저지연 실시간 틱 데이터 기반 비동기 통합 봇 실행
PYTHONPATH=. python3 scripts/live_bot_async.py
```

### 4. 실시간 포트폴리오 대시보드
```bash
# 브라우저에서 http://localhost:5000 접속
PYTHONPATH=. python3 scripts/dashboard.py
```

## 📂 프로젝트 구조

- **scripts/live_bot_async.py**: 차세대 비동기 웹소켓 통합 매매 엔진 (V7 핵심)
- **src/portfolio_manager_async.py**: 비동기 안전 자본 관리자
- **src/websocket_manager.py**: 바이낸스 선물 실시간 스트림 관리자
- **src/db_manager.py**: 상태 영속화 및 수익 기록 엔진
- **tests/**: 27개의 검증된 Unit/Integration 테스트

---
*Disclaimer: 본 소프트웨어는 기술적 분석 도구이며, 모든 투자의 책임은 사용자 본인에게 있습니다.*
