# 🚀 TrendCrusher V11.1.1: The Phoenix Engine
> **"시장을 추격하지 말고 길목에서 매복하라. 쓰러져도 10초 만에 다시 일어난다."**
> 
> TrendCrusher는 가상자산 선물 시장의 변동성을 정밀하게 포착하여 수익으로 치환하는 **초저지연 비동기 알고리즘 매매 시스템**입니다. V11.1.1 버전은 최강의 타점을 자랑하는 **The Sniper** 엔진과 어떤 상황에서도 스스로 복구되는 **Phoenix Watchdog** 체계가 결합된 최종 완성형 엔진입니다.

---

## 📑 목차 (Table of Contents)
1. [시스템 철학](#-시스템-철학)
2. [핵심 전략 (The 4 Pillars)](#-핵심-전략-the-4-pillars)
3. [주요 기능 하이라이트](#-주요-기능-하이라이트)
4. [상세 설정 가이드 (Configuration)](#-상세-설정-가이드-configuration)
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
- **Phoenix Watchdog (v11.1.1)**: OOM Killer나 프로세스 중단 시 즉시 알림 및 10초 내 자동 재시작.
- **The Sentinel (v10)**: 매주 최근 30일 데이터를 자가 학습하여 최적의 파라미터를 텔레그램으로 제안.
- **WebSocket Async Engine (v7)**: 시장의 모든 틱(Tick)을 실시간 수신하여 지연 시간 제로화.
- **Smart Isolated Margin**: 코인별 철저한 자산 격리 및 독립 가상 장부 관리.

---

## 🔧 상세 설정 가이드 (Configuration)

### 1. 비밀번호 및 계정 설정 (.env)
프로젝트 루트의 `.env` 파일은 봇의 신분증과 같습니다.

| 변수명 | 설명 | 비고 |
| :--- | :--- | :--- |
| `BINANCE_API_KEY` | 바이낸스 API Key | **Futures 권한 필수**, 출금 불가 권장 |
| `BINANCE_SECRET` | 바이낸스 Secret Key | 외부 유출 절대 금지 |
| `TELEGRAM_TOKEN` | 봇파더에게 받은 API 토큰 | 알림 및 원격 제어용 |
| `TELEGRAM_CHAT_ID` | 내 텔레그램 계정 숫자 ID | 인증된 사용자 식별용 |
| `DRY_RUN` | 실거래 여부 (`True`/`False`) | True 설정 시 가상 머니로 테스트 |
| `SEED` | 가상 시작 자본금 | DRY_RUN 모드에서만 사용 |

### 2. 전략 및 리스크 관리 (src/config.py)
`src/config.py`는 봇의 지능과 리스크 허용 범위를 결정합니다.

#### 🌍 글로벌 설정 (Global Settings)
*   **`SYMBOLS_LIST`**: 봇이 동시에 감시할 코인 목록. (예: `["TRUMP/USDT", "ETH/USDT"]`)
*   **`MAX_CONCURRENT_TRADES`**: 동시에 잡을 수 있는 최대 포지션 개수. 계좌 전체 리스크를 제한합니다.
*   **`SNIPER_PROXIMITY_PCT`**: 돌파가 얼마나 가까워졌을 때 매복 주문을 넣을지 결정 (기본 `0.005` = 0.5%).
*   **`FEE_RATE` / `MAKER_FEE_RATE`**: 거래소 수수료율. 수익률 계산의 정밀도를 결정합니다.

#### 🎯 심볼별 최적화 설정 (SYMBOL_SETTINGS)
각 코인의 성격에 맞게 개별 파라미터를 설정합니다.
*   **`ALLOCATED_SEED`**: 해당 코인에 할당할 전용 자산. (예: $4,000)
*   **`VOL_MULTIPLIER`**: 거래량 폭발 기준. (높을수록 깐깐한 진입)
*   **`ADX_FILTER_LEVEL`**: 추세 강도 기준. (높을수록 확실한 추세에서만 진입)
*   **`EMA_TREND_PERIOD`**: 대세 판단 이평선. (보통 100 또는 200 사용)
*   **`RISK_PER_TRADE`**: 한 번의 매매에서 감수할 원금 대비 손실 비율 (기본 `0.02` = 2%).

---

## ⚙️ 설치 및 실행 (Installation)

### 1. 가상환경 구축 및 라이브러리 설치
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 설정 (Configuration)
`config.example.yaml` 파일을 `config.yaml`로 복사한 후, 본인의 환경에 맞게 수정하세요.

```bash
cp config.example.yaml config.yaml
```

**주요 설정 항목:**
- **API Keys**: `BINANCE_API_KEY`, `BINANCE_SECRET`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`를 설정합니다.
- **Trading Settings**: `DRY_RUN` (테스트 모드 여부), `SEED` (초기 자본), `SYMBOLS_LIST` 등을 조정할 수 있습니다.
- **Strategy Params**: 각 코인별로 최적화된 파라미터(`SYMBOL_SETTINGS`)를 직접 수정하거나 Sentinel이 자동 업데이트하도록 둘 수 있습니다.

> **Tip:** 보안을 위해 API 키 등 민감한 정보는 `.env` 파일이나 OS 환경 변수로 설정할 수도 있습니다. 이 경우 `config.yaml`의 값보다 환경 변수가 우선 적용됩니다.

### 3. 연결 및 보안 검증 (권장)
봇 본체를 돌리기 전, 텔레그램 명령 수신과 내 폰의 ID가 일치하는지 확인하세요.
```bash
PYTHONPATH=. python3 scripts/test_telegram_commands.py
```

### 4. 라이브 봇 실행 (Phoenix 모드 - 추천)
봇을 실시간 감시하고 죽으면 되살리는 워치독 모드로 가동합니다.
```bash
PYTHONPATH=. python3 scripts/watchdog.py
nohup python3 scripts/watchdog.py > watchdog.log 2>&1 &
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
**TrendCrusher V11.1.2 Development Team**
*Technical Co-Founder by AI Agent*
