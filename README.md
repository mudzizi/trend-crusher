# TrendCrusher V6: Smart Isolated Independent Trading System

TrendCrusher는 가상자산 선물 시장을 위한 프로페셔널 자동 매매 엔진입니다. V6 버전에서는 각 코인이 마치 독립된 계좌에서 돌아가는 것과 같은 **Smart Isolated** 마진 체계와 **독립 자본 관리** 로직을 완성했습니다.

## 🚀 주요 특징 (V6 핵심)

- **Smart Isolated Margin (V6 New)**: 포지션이 없는 코인 진입 시 자동으로 격리 마진(Isolated)을 설정하여 타 종목으로의 리스크 전이를 원천 차단.
- **Independent Capital Isolation (V6 New)**: 코인별 `ALLOCATED_SEED` 기반의 독립 가상 장부 관리. 한 코인의 수익/손실이 다른 코인의 포지션 사이즈에 영향을 주지 않음.
- **Crash Recovery & Persistence (V6 New)**: 봇 재시작 시 0.1초 전의 상태(최고가, 손절 주문 ID 등)를 완벽히 복구하는 DB 영속화 엔진.
- **Real-time Portfolio Dashboard**: 전체 자산 현황, 심볼별 수익 곡선, 활성 포지션의 수익률을 한눈에 모니터링.
- **Dual Constraint Sizing**: 리스크(2%)와 가용 증거금 한도 중 더 안전한 값을 자동으로 선택.
- **Adaptive Trailing Stop**: 수익 구간에 따라 ATR 추격 거리를 타이트하게 조절하여 수익 보존.

## 📊 최신 검증 성과 (365일 / S-Tier)

- **TRUMP/USDT**: 수익률 **+210.07%** | MDD 17%
- **XAU/USDT**: 수익률 **+186.89%** | MDD **12%**
- **ETH/USDT**: 수익률 **+161.44%** | MDD 19%

## 🛠 설치 및 실행

### 1. 환경 설정
`.env` 파일에 API 키와 텔레그램 정보를 입력하세요.

### 2. 가상환경 및 설치
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 라이브 봇 실행 (V6 통합 엔진)
```bash
# 여러 코인을 독립적으로 감시하며 자본을 격리 매매하는 통합 봇
PYTHONPATH=. python3 scripts/live_bot_multi.py
```

### 4. 실시간 포트폴리오 대시보드
```bash
# 브라우저에서 http://localhost:5000 접속
PYTHONPATH=. python3 scripts/dashboard.py
```

## 📂 프로젝트 구조

- **src/portfolio_manager.py**: 독립 자본 관리 및 리스크 제어 (V6 핵심)
- **src/db_manager.py**: 상태 복구 및 심볼별 수익 기록 엔진
- **scripts/live_bot_multi.py**: 멀티 심볼 스마트 격리 매매 오케스트레이터
- **tests/**: 27개의 검증된 유닛/통합 테스트 케이스

---
*Disclaimer: 본 소프트웨어는 기술적 분석 도구이며, 모든 투자의 책임은 사용자 본인에게 있습니다.*
