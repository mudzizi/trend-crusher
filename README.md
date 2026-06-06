# 🚀 TrendCrusher V13.3.8: The Resilience Update
> **"지표는 1시간을 보되, 실행은 1초를 앞서간다."**
> 
> TrendCrusher는 가상자산 선물 시장의 변동성을 정밀하게 포착하여 수익으로 치환하는 **초저지연 비동기(Async) 알고리즘 매매 시스템**입니다. v13.3.8 버전은 V7.0 Chaos & Squeeze 엔진을 기반으로, API 부하 최적화와 완벽한 거래소 동기화를 달성한 **운영 리질리언스(Resilience) 완성판**입니다.
---

## 📑 목차 (Table of Contents)
1. [시스템 철학](#-시스템-철학)
2. [핵심 전략 (The 4 Pillars)](#-핵심-전략-the-4-pillars)
3. [주요 기능 하이라이트](#-주요-기능-하이라이트)
4. [상세 설정 가이드 (Configuration)](#-상세-설정-가이드-configuration)
5. [설치 및 실행 (Installation)](#-설치-및-실행-installation)
6. [운영 및 안전 (Operations & Safety)](#-운영-및-안전-operations--safety)
7. [성능 벤치마크 (Performance)](#-성능-벤치마크-performance)
8. [주의사항 및 면책조항 (Disclaimer)](#-주의사항-및-면책조항-disclaimer)

---

## 🎯 시스템 철학
시장의 'Taker'가 아닌 'Maker'가 되는 것을 목표로 합니다. 단순히 가격이 오를 때 추격 매수하는 것이 아니라, 강력한 추세가 형성되는 길목에 **정확한 돌파 가격으로 미리 지정가(Limit)를 배치**하는 'Sniper' 전략을 구사합니다. 이를 통해 슬리피지를 최소화하고 수수료 리베이트를 확보하여 매매 우위를 점합니다.

---

## 🧠 핵심 전략 (The 4 Pillars)
진입 신호는 **1시간봉(1h) 기준의 기술적 지표**를 바탕으로 하되, **웹소켓 실시간 데이터**를 결합하여 캔들 중간에도 즉각 대응합니다.

1.  **Chaos Index Filter (V7.0)**: 단순 추세 강도가 아닌, 시장의 불균형이 극에 달한 '카오스' 구간을 감지하여 에너지 폭발 직전의 신호만 선별.
2.  **Volatility Squeeze Breakout**: 볼린저 밴드가 켈트너 채널 내부로 수렴하여 에너지가 응축된 상태에서 터지는 변동성 돌파 포착.
3.  **Asymmetric Short Bias**: 하락장의 속도가 더 빠르다는 특성을 반영하여 숏 진입 시 문턱값을 자동으로 낮추는 비대칭 로직.
4.  **EMA Macro Filter**: 4시간봉(4h) 장기 이평선을 통해 대세 추세 방향을 판별하여 역추세 매매 원천 방지.

---

## 🛡️ 주요 기능 하이라이트
- **Intelligent API Scaling**: 메모리 기반 데이터 업데이트로 바이낸스 Rate Limit 에러 및 프로세스 Crash(Exit -9) 원천 차단.
- **Nuclear Order Safety**: 중복 주문 방지를 위한 `cancel_all_orders` 선제 클린업 로직 및 SSOT(Single Source of Truth) 동기화.
- **Turbo-Charged Numba Engine**: 고속 연산 엔진을 통해 백테스트와 라이브 간의 로직 오차 0% 구현 및 나노초 단위 정밀도 확보.
- **Financial Parity**: Maker(0.02%) 및 Taker(0.05%) 수수료 차등 적용으로 실전 계좌와 백테스트 간 경제적 일관성 100% 확보.
- **100% Test Validation**: 78개의 포괄적인 테스트 스위트 통과로 검증된 시스템 무결성 (Zero Regression).

---

## 🔧 상세 설정 가이드 (Configuration)

모든 설정은 프로젝트 루트의 `config.yaml` 파일에서 한곳에 관리됩니다.

### 1. 설정 파일 생성
`config.example.yaml`을 복사하여 본인의 환경에 맞는 `config.yaml`을 만듭니다.
```bash
cp config.example.yaml config.yaml
```

---

## 🚀 설치 및 실행 (Installation)

### 1. 가상환경 구축
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 라이브 봇 실행 (Async Core)
```bash
PYTHONPATH=. python3 scripts/live_bot_async.py
```

### 3. 백테스트 및 최적화
```bash
# 특정 종목 백테스트
python3 scripts/backtest.py --symbol TRUMP/USDT --days 365

# 파라미터 최적화 (Optuna)
python3 scripts/optimize.py --symbol ETH/USDT --trials 100
```

---

## 🛡️ 운영 및 안전 (Operations & Safety)
- **Phoenix Watchdog**: 봇의 생존 여부를 1초마다 감시하여 Crash 발생 시 즉시 자동 재시작.
- **Telegram Command**: `/status`, `/close_all`, `/sniper_on` 등 원격 제어 인터페이스 제공.
- **Risk Guard**: 단일 종목 최대 노출액(`MAX_POSITION_VALUE_USDT`) 제한 기능.

---

## 📊 성능 벤치마크 (Performance)
(v13.3.8 엔진, 리스크 2.0% 기준 2년 성과)

| 종목 | 누적 수익률 | 최대 낙폭 (MDD) | 거래 횟수 | 효율 (Ret/MDD) |
| :--- | :---: | :---: | :---: | :---: |
| **TRUMP/USDT** | **+139.55%** | 27.81% | 178회 | 5.00 |
| **BTC/USDT** | **+42.12%** | 15.30% | 120회 | 2.75 |

---

## ⚠️ 주의사항 및 면책조항 (Disclaimer)
- 본 소프트웨어는 교육 및 연구 목적으로 제작되었습니다.
- 모든 투자의 책임은 사용자 본인에게 있으며, 시장 상황에 따라 원금 손실이 발생할 수 있습니다.
- API Key 유출에 주의하고, 초기 구동 시 `DRY_RUN: true` 설정을 권장합니다.
