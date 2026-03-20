# 🚀 TrendCrusher V11.0.1: The Phoenix Engine
> **"시장을 추격하지 말고 길목에서 매복하라. 쓰러져도 10초 만에 다시 일어난다."**
> 
> TrendCrusher는 가상자산 선물 시장의 변동성을 정밀하게 포착하여 수익으로 치환하는 **초저지연 비동기 알고리즘 매매 시스템**입니다. V11.0.1 버전은 최강의 타점을 자랑하는 **The Sniper** 엔진과 어떤 상황에서도 스스로 복구되는 **Phoenix Watchdog** 체계가 결합된 최종 완성형 엔진입니다.

---

## 📑 목차 (Table of Contents)
1. [시스템 철학](#-시스템-철학)
2. [핵심 전략 (The 4 Pillars)](#-핵심-전략-the-4-pillars)
3. [주요 기능 하이라이트](#-주요-기능-하이라이트)
4. [환경 설정 가이드 (.env Setup)](#-환경-설정-가이드-env-setup)
5. [설치 및 실행 (Installation)](#-설치-및-실행-installation)
6. [운영 마스터 가이드 (Operations)](#-운영-마스터-가이드-operations)
7. [안전 및 회복력 (Safety)](#-안전-및-회복력-safety)
8. [성능 벤치마크 (Performance)](#-성능-벤치마크-performance)
9. [주의사항 및 면책조항 (Disclaimer)](#-주의사항-및-면책조항-disclaimer)

---

## 🎯 시스템 철학
대부분의 자동매매 봇은 돌파가 일어난 **후**에 시장가로 따라붙습니다. 이는 슬리피지와 높은 수수료라는 독배를 마시는 행위입니다. TrendCrusher는 돌파의 전조 현상을 감지하여 **정확한 돌파 가격에 미리 지정가(Limit)를 배치**합니다. 우리는 시장의 'Taker'가 아닌 'Maker'로서, 수수료 리베이트를 챙기고 가장 유리한 평단가를 선점합니다.

---

## 🧠 핵심 전략 (The 4 Pillars)
모든 진입은 다음 4가지 조건이 1분 단위로 완벽하게 일치할 때만 실행됩니다.

1.  **Donchian Channel Breakout**: 직전 20개 봉의 고점/저점을 뚫는 모멘텀 포착.
2.  **Volume Burst Filter**: 거래량이 평균 대비 **2.0~2.5배 이상** 폭발하며 에너지가 응축될 때만 진입.
3.  **ADX Trend Strength**: ADX(14) 지표를 통해 힘없는 박스권 돌파를 배제하고 강력한 추세에만 탑승.
4.  **EMA Macro Filter**: 4시간봉 대이평선을 통해 시장의 큰 흐름(장기 방향성)과 일치할 때만 배팅.

---

## 🛡️ 주요 기능 하이라이트
- **The Precision Sniper (v11)**: 돌파 레벨 0.5% 근접 시 자동 매복. 조건 불일치 시 0.1초 만에 즉시 취소.
- **Phoenix Watchdog (v11.0.1)**: OOM Killer나 프로세스 중단 시 즉시 알림 및 10초 내 자동 재시작.
- **The Sentinel (v10)**: 매주 최근 30일 데이터를 자가 학습하여 최적의 파라미터를 텔레그램으로 제안.
- **WebSocket Async Engine (v7)**: 시장의 모든 틱(Tick)을 실시간 수신하여 지연 시간 제로화.
- **Smart Isolated Margin**: 코인별 철저한 자산 격리 및 독립 가상 장부 관리.

---

## 🛠 환경 설정 가이드 (.env Setup)
프로젝트 루트에 `.env` 파일을 생성하고 아래 형식을 복사하여 입력하세요.

```env
# 바이낸스 선물 API 키 (필수)
BINANCE_API_KEY=your_api_key_here
BINANCE_SECRET=your_secret_key_here

# 텔레그램 알림 및 원격 제어 (필수)
TELEGRAM_TOKEN=12345678:ABCdefGHI...
TELEGRAM_CHAT_ID=123456789

# 가상 매매 여부 (True: 테스트 / False: 실제 돈)
DRY_RUN=True

# 초기 가상 자본 (DRY_RUN 모드 전용)
SEED=10000
```

---

## ⚙️ 설치 및 실행 (Installation)

### 1. 가상환경 구축 및 라이브러리 설치
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 연결 및 보안 검증 (권장)
봇 본체를 돌리기 전, 텔레그램 명령 수신과 내 폰의 ID가 일치하는지 확인하세요.
```bash
PYTHONPATH=. python3 scripts/test_telegram_commands.py
```

### 3. 라이브 봇 실행 (Phoenix 모드 - 추천)
봇을 실시간 감시하고 죽으면 되살리는 워치독 모드로 가동합니다.
```bash
PYTHONPATH=. python3 scripts/watchdog.py
```

---

## 📱 운영 마스터 가이드 (Operations)

### 텔레그램 원격 명령어 리스트
| 명령어 | 설명 | 활용 팁 |
| :--- | :--- | :--- |
| `/status` | 전체 자산 현황 및 매복 상태 보고 | 현재 수익률과 매복 여부 확인 |
| `/optimize [SYM]` | 해당 코인의 파라미터 재학습 지시 | 시장 성격이 변했을 때 사용 |
| `/apply [SYM]` | 봇이 제안한 파라미터를 즉시 반영 | Sentinel 제안 수락 시 |
| `/sniper_on/off` | 선제적 지정가 매복 기능 제어 | 휩소 장세가 심할 때 OFF 가능 |
| `/stop` / `/resume` | 신규 진입 로직 중단 및 재개 | 큰 발표(CPI 등) 전 일시 중단 |
| `/close_all` | **[긴급 킬 스위치]** 전량 청산 및 종료 | 비상 사태 시 사용 |

### 자가 학습 워크플로우 (Sentinel)
1. 봇이 매주 월요일 00:00에 자동 스캔을 수행하거나, 사용자가 `/optimize` 명령을 내립니다.
2. 봇이 "이런 세팅이 더 좋습니다"라고 리포트를 보냅니다.
3. 리포트의 예상 수익률/MDD를 확인하고 `/apply`를 입력하여 전략을 즉시 갱신합니다.

---

## 🛡️ 안전 및 회복력 (Safety)
- **Last Will (유언)**: 봇이 예상치 못한 에러로 죽기 직전, 에러 원인을 텔레그램으로 전송합니다.
- **Atomic Order**: 진입 주문 성공 후 손절(SL) 주문 배치가 실패하면, 자산 보호를 위해 잡았던 포지션을 즉시 강제 종료합니다.
- **Isolated Margin**: 한 종목의 100% 손실이 발생하더라도, 다른 종목의 자산에는 손끝 하나 대지 못하도록 물리적으로 격리합니다.

---

## 📊 성능 벤치마크 (Performance)
*가혹한 시장 조건(슬리피지 0.5%) 하에서의 1년 누적 백테스트 결과*

| 종목 | 일반 시장가 모드 | **스나이퍼 모드 (Limit)** | **Alpha (수익 향상)** |
| :--- | :---: | :---: | :---: |
| **TRUMP/USDT** | +83.89% | **+835.82%** | **+751%** |
| **ETH/USDT** | +39.69% | **+676.17%** | **+636%** |
| **XAU/USDT** | -13.93% | **+343.27%** | **+357%** |

---

## ⚠️ 주의사항 및 면책조항 (Disclaimer)
1.  **Slippage Risk**: 스나이퍼 모드라도 거래량이 전무한 시점에는 지정가 체결이 밀릴 수 있습니다.
2.  **API Security**: `BINANCE_API_KEY`는 반드시 선물 매매 권한만 부여하고, **출금 권한은 절대 부여하지 마세요.**
3.  **Funding Fee**: 장기 보유 시 펀딩비가 발생하며, 이는 수익률을 갉아먹는 요인이 됩니다.
4.  **No Guarantee**: 본 소프트웨어는 과거 데이터를 기반으로 최적화되었으나, 미래의 수익을 보장하지 않습니다. 모든 투자의 책임은 사용자 본인에게 있습니다.

---
**TrendCrusher V11.0.1 Development Team**
*Technical Co-Founder by AI Agent*
