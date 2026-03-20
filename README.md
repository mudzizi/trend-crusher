# TrendCrusher V11: The Precision Sniper

TrendCrusher는 가상자산 선물 시장을 위한 인텔리전트 자동 매매 시스템입니다. V11 버전에서는 **The Sniper (선제적 지정가 매복 시스템)**를 도입하여, 돌파가 일어나는 정확한 찰나에 Maker 수수료를 받으며 슬리피지 없이 진입하는 완벽한 타점 알고리즘을 완성했습니다.

## 🚀 주요 특징 (V11 핵심)

- **The Precision Sniper (v11.0.0 New)**: 시장가 추격을 버리고, 돌파 직전(99.5%)에 4대 기둥(Volume, ADX, EMA)이 일치할 때만 전고점에 지정가(Maker)로 매복하는 선제 진입 시스템.
- **The Sentinel (v10)**: 매주 정기 스캔 및 성과 하락 시 긴급 재최적화를 수행하고 제안서를 발송하는 지능형 파수꾼.
- **Human-in-the-Loop Control**: 봇의 지능(제안)과 사람의 직관(승인)이 결합된 가장 안전한 자동화.
- **WebSocket Async Engine**: 밀리초(ms) 단위의 반응 속도로 틱 데이터 실시간 처리.
- **Atomic Order Safety**: 진입-손절 배치를 하나의 원자적 단위로 관리.
- **Smart Isolated Margin & Persistent State**: 철저한 자산 격리와 0.1초 단위의 상태 복구 시스템.

## 📊 최신 검증 성과 (365일 / S-Tier)

- **TRUMP/USDT**: 수익률 **+210.07%** | MDD 17.29%
- **XAU/USDT**: 수익률 **+186.89%** | MDD **12.55%**
- **ETH/USDT**: 수익률 **+161.44%** | MDD 19.80%

---

## 📱 Telegram 원격 지휘 및 운영 가이드

TrendCrusher V11은 텔레그램을 통해 전 세계 어디서나 봇을 지휘할 수 있는 강력한 인터페이스를 제공합니다.

### 1. 기본 모니터링
*   **/status**: 모든 코인의 포지션 상태, 수익률, 스나이퍼 매복 상태(🎯 AMBUSHING), 최적화 제안 대기 여부를 요약 보고.
*   **Hourly Heartbeat**: 매 1시간마다 봇이 포트폴리오 요약을 자동으로 전송.

### 2. 지능형 최적화 (The Sentinel)
*   **/optimize [SYMBOL]**: 수동으로 최적화를 지시합니다. (예: `/optimize ETH/USDT`)
*   **/apply [SYMBOL]**: 봇이 제안한 최적 파라미터를 즉시 실전에 적용(Hot-Reload)합니다.
*   **/reject [SYMBOL]**: 봇의 제안을 거절하고 현재 설정을 유지합니다.

### 3. 긴급 통제 및 스나이퍼 제어
*   **/sniper_off**: 스나이퍼 매복 모드를 끄고, 돌파 확인 후 즉시 시장가 진입하는 공격적 모드로 전환.
*   **/sniper_on**: 선제적 지정가 매복(Maker) 모드 활성화.
*   **/stop**: 새로운 진입 신호(Entry)만 중단 (기존 포지션은 계속 추적).
*   **/resume**: 중단된 진입 로직 재가동.
*   **/close_all**: **[긴급 킬 스위치]** 모든 포지션을 즉시 시장가로 종료하고, 대기 주문을 취소한 뒤 봇 프로세스를 안전하게 중단합니다.

### 🔒 보안 안내
*   봇은 오직 설정파일(`config.py`)에 등록된 **TELEGRAM_CHAT_ID**의 메시지만 수행합니다. 타인의 명령은 철저히 무시되며 경고 로그가 남습니다.

---

## 🛠 설치 및 실행

### 1. 연결 확인 (추천)
봇 본체를 돌리기 전, 텔레그램 명령이 잘 수신되는지 확인하세요.
```bash
PYTHONPATH=. python3 scripts/test_telegram_commands.py
```

### 2. 라이브 봇 실행
```bash
# V11 지능형 통합 엔진 가동 (스나이퍼 매복 모드 기본 활성)
PYTHONPATH=. python3 scripts/live_bot_async.py
```

## 📂 프로젝트 구조

- **scripts/test_telegram_commands.py**: 실시간 명령 수신 검증기
- **src/optimizer_engine.py**: 자가 적응형 파라미터 최적화 엔진
- **scripts/live_bot_async.py**: 지능형 비동기 웹소켓 통합 매매 엔진 (Sniper 탑재)
- **tests/**: 34개의 검증된 Unit/Integration 테스트 케이스

---
*Disclaimer: 본 소프트웨어는 기술적 분석 도구이며, 모든 투자의 책임은 사용자 본인에게 있습니다.*
