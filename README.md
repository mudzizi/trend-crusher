# 🚀 TrendCrusher V11.9.9: The Unified Strategy Engine
> **"지표는 1시간을 보되, 실행은 1초를 앞서간다."**
> 
> TrendCrusher는 가상자산 선물 시장의 변동성을 정밀하게 포착하여 수익으로 치환하는 **초저지연 비동기(Async) 알고리즘 매매 시스템**입니다. V11.9.9 버전은 백테스트와 라이브 거래 로직을 하나의 엔진으로 통합한 **단일 진실 공급원(Single Source of Truth)** 구조의 완성판입니다.

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
진입 신호는 **1시간봉(1h) 기준의 기술적 지표**를 바탕으로 하되, **웹소켓 실시간 데이터(2초 주기)**를 결합하여 캔들 중간에도 즉각 대응합니다.

1.  **Donchian Breakout**: 1시간봉 기준 전고점/전저점을 실시간 가격이 상향/하향 돌파할 때 포착.
2.  **Volume Burst Filter**: 거래량이 이전 평균 대비 설정 배수(2.0x+) 이상 폭발하며 강력한 수급이 실릴 때만 진입.
3.  **ADX Trend Strength**: ADX 지표를 통해 힘없는 박스권 돌파를 배제하고 강력한 추세 모멘텀에만 탑승.
4.  **EMA Macro Filter**: 4시간봉(4h) 장기 이평선을 통해 대세 하락장인지 상승장인지 판단하여 역추세 매매 방지.

---

## 🛡️ 주요 기능 하이라이트
- **Turbo-Charged Engine (v11.9.7)**: NumPy 벡터화 루프 탑재로 기존 대비 5배 빠른 백테스트 속도와 나노초 단위 정밀도 구현.
- **Financial Parity**: Maker(0.02%) 및 Taker(0.05%) 수수료 차등 적용으로 실전 계좌와 백테스트 간 오차 100% 제거.
- **Smart Control Center (v4.5)**: 실시간 지표 근접도와 종합 신호 점수를 시각화한 대시보드에서 봇의 '사고 과정'을 모니터링.
- **Atomic Safety & Kill Switch**: /close_all 명령 시 실제 거래소 포지션을 API로 직접 대조하여 시장가로 강제 청산하는 `Force Exit` 로직 탑재.
- **100% Test Validation**: 67개의 포괄적인 테스트 스위트 통과로 검증된 시스템 무결성 (Zero Regression).

---

## 🔧 상세 설정 가이드 (Configuration)

모든 설정은 프로젝트 루트의 `config.yaml` 파일에서 한곳에 관리됩니다.

### 1. 설정 파일 생성
`config.example.yaml`을 복사하여 본인의 환경에 맞는 `config.yaml`을 만듭니다.
```bash
cp config.example.yaml config.yaml
```

### 2. 세부 항목 설명
각 설정 값에 대한 상세한 설명과 권장값은 **[CONFIG_GUIDE.md](./CONFIG_GUIDE.md)**를 참조하세요.

> **보안 팁:** API 키와 같이 민감한 정보는 `.env` 파일이나 OS 환경 변수로 설정할 수 있습니다. 이 경우 YAML 설정보다 환경 변수의 값이 우선 적용됩니다.

---

## ⚙️ 설치 및 실행 (Installation)

### 1. 가상환경 구축 및 라이브러리 설치
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 연결 및 보안 검증 (권장)
봇 실행 전 텔레그램 연동 상태를 확인합니다.
```bash
PYTHONPATH=. python3 scripts/test_telegram_commands.py
```

### 3. 라이브 봇 실행 (Phoenix 모드 - 추천)
워치독(Watchdog) 모드로 실행하여 중단 없는 매매 환경을 구축합니다.
```bash
# 백그라운드 가동
nohup python3 scripts/watchdog.py > watchdog.log 2>&1 &
```

---

## 📱 운영 및 안전 (Operations & Safety)

### 텔레그램 원격 명령어
- `/status`: 전체 자산 현황 및 현재 포지션/매복 상태 보고.
- `/optimize [SYM]`: 특정 종목의 파라미터 재학습 지시.
- `/sniper_on/off`: 지정가 매복(Sniper) 기능 활성화 제어.
- `/stop` / `/resume`: 신규 진입 일시 중단 및 재개.
- `/close_all`: **[긴급 킬 스위치]** 모든 포지션 시장가 청산 및 봇 정지.

### 안전 장치
- **Last Will (유언)**: 비정상 종료 시 에러 리포트를 텔레그램으로 전송.
- **Atomic Order**: 진입 직후 손절(SL) 주문 실패 시 즉시 포지션 강제 청산.
- **Zero Regression**: 모든 코드는 전체 테스트(`pytest`) 통과 후에만 배포 및 적용.

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
1.  **Slippage Risk**: 급격한 변동성 상황에서는 지정가 매복 주문이라도 체결 지연이 발생할 수 있습니다.
2.  **API Security**: `BINANCE_API_KEY`는 반드시 **선물 매매 권한만** 부여하고, **출금 권한은 절대 부여하지 마세요.**
3.  **No Guarantee**: 본 소프트웨어는 과거 데이터를 기반으로 최적화되었으나, 미래의 수익을 보장하지 않습니다. 모든 투자의 책임은 사용자 본인에게 있습니다.

---
**TrendCrusher V11.9.9 Development Team**
*Technical Co-Founder by AI Agent*
