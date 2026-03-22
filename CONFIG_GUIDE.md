# 🛠️ TrendCrusher V11.9.0: Configuration Guide

이 가이드는 `config.yaml` 파일에 포함된 모든 설정 항목의 의미, 작동 방식 및 권장값을 상세히 설명합니다. v11.9.0 리팩토링을 통해 **신호 안정성(Hysteresis)** 기능이 추가되었습니다.

---

## 1. 🔑 API & Security (보안 및 연동)

| 항목 | 설명 | 권장값 / 주의사항 |
| :--- | :--- | :--- |
| `BINANCE_API_KEY` | 바이낸스 선물 거래 API 키 | **선물(Futures) 권한 필수.** 출금 권한은 반드시 해제하세요. |
| `BINANCE_SECRET` | 바이낸스 API 시크릿 | 절대 외부로 유출하지 마세요. |
| `TELEGRAM_TOKEN` | 텔레그램 봇 API 토큰 | @BotFather를 통해 발급받은 문자열. |
| `TELEGRAM_CHAT_ID` | 알림을 받을 사용자 ID | @userinfobot 등을 통해 확인한 본인의 숫자 ID. |

---

## 2. 🚀 Strategy Modes (진입 모드 설정)

TrendCrusher는 세 가지 진입 방식을 지원합니다. 전역 설정(`USE_SNIPER` 등)보다 `SYMBOL_SETTINGS` 내의 개별 설정이 우선합니다.

| 모드 | 설정값 (`Sniper` / `Retest`) | 설명 | 수수료/슬리피지 |
| :--- | :--- | :--- | :--- |
| **Market** | `false` / `false` | 캔들 마감 시 조건 충족하면 즉시 시장가 진입. | Taker 수수료 / 높은 슬리피지 |
| **Sniper** | **`true`** / `false` | 돌파가 임박(`Proximity`)하면 미리 지정가를 걸어 매복. | **Maker 수수료** / 제로 슬리피지 |
| **Retest** | `false` / **`true`** | 돌파 후 다시 돌파 레벨로 가격이 되돌아올 때 지정가 진입. | **Maker 수수료** / 최저 리스크 |

> **v11.9.0 Update**: Sniper/Retest 대기 중에는 **히스테리시스**가 적용되어, `SNIPER_PROXIMITY_PCT` 기준의 2배(최대 1.0%)까지 가격이 벌어져도 주문을 유지합니다.

---

## 3. 🧠 SYMBOL_SETTINGS (코인별 개별 설정)

특정 코인의 특성에 맞춰 전역 설정을 덮어쓸 수 있습니다.

```yaml
SYMBOL_SETTINGS:
  "BTC/USDT":
    USE_RETEST_MAKER: true  # 비트코인은 리테스트 시에만 진입하여 안정성 확보
    EMA_TREND_PERIOD: 200   # 더 긴 호흡의 추세 필터 적용
    ALLOCATED_SEED: 3000.0  # 이 종목에만 할당할 자산
  "TRUMP/USDT":
    USE_SNIPER: false       # 변동성이 큰 알트코인은 시장가로 확실히 체결
    VOL_MULTIPLIER: 3.0     # 더 강력한 거래량 폭발 요구
```

---

## 4. 🕒 Timeframes & Intervals (주기 설정)

| 항목 | 설명 | 권장값 / 주의사항 |
| :--- | :--- | :--- |
| `SIGNAL_TIMEFRAME` | 메인 신호 발생 주기 | **`1h`**. 너무 짧으면 노이즈가 많고, 길면 진입 기회가 적음. |
| `TREND_TIMEFRAME` | 대세 판단 주기 | **`4h`**. 메인 주기보다 긴 타임프레임으로 추세 필터링. |
| `CHECK_TIMEFRAME` | 내부 연산 최소 주기 | **`1m`**. 백테스트 검증 및 내부 계산용. |

---

## 5. 🛡️ Risk & Trailing (리스크 관리)

| 항목 | 설명 | 권장값 / 주의사항 |
| :--- | :--- | :--- |
| `RISK_PER_TRADE` | 회당 리스크 비중 | **`0.02`** (2%). 손절 시 전체 자산의 2%만 손실되도록 수량 조절. |
| `INITIAL_SL_ATR` | 초기 손절폭 (ATR 배수) | `2.0`. 진입가 기준 `2.0 * ATR` 거리에 손절선 배치. |
| `USE_ADAPTIVE_TRAIL` | 적응형 트레일링 사용 | **`true`**. 수익이 날수록 익절선을 타이트하게 올림. |
| `ADAPTIVE_TRAIL_STEPS` | 트레일링 단계 설정 | `tighten_ratio`를 통해 구간별로 ATR 배수를 줄여 수익 보존. |

---

## 💎 전략적 설정 팁 (Strategy Tips)

1.  **메이저 코인 (BTC, ETH)**: `USE_RETEST_MAKER` 또는 `USE_SNIPER`를 사용하여 Maker 수수료 혜택을 극대화하세요.
2.  **급등주/알트코인**: 돌파 시 가격이 순식간에 멀어질 수 있으므로 `Market` 진입(둘 다 false)이 유리할 수 있습니다.
3.  **손절 방어**: `INITIAL_SL_ATR`은 최소 1.5 이상을 권장합니다. 너무 낮으면 시장의 일시적인 노이즈에 털릴 수 있습니다.

---
**주의:** 모든 설정 변경 후에는 반드시 `python3 backtest/precision_backtester.py`를 통해 시뮬레이션 결과를 먼저 확인하십시오.
