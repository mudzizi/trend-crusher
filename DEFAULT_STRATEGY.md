# TrendCrusher Default Strategy

## 목적
이 문서는 현재 저장소에서 기본 전략으로 간주하는 운용 기준을 고정하기 위한 문서다.
백서가 연구 결과를 설명한다면, 이 문서는 실제 백테스트와 운영에 사용할 기본값을 기록한다.

기준 시점: 2026-03-18

## 공통 전략 구조
- 거래소: Binance USDT-M Futures
- 시그널 봉: `1h`
- 추세 확인 봉: `4h`
- 정밀 체결 확인 봉: `1m`
- 진입 조건:
  - `20`봉 Donchian 상단 돌파 시 LONG 후보
  - `20`봉 Donchian 하단 이탈 시 SHORT 후보
  - 거래량이 직전 `20`봉 평균 대비 설정 배수 이상일 때만 진입
  - `4h EMA` 위 돌파는 LONG, 아래 이탈은 SHORT만 허용
- 청산 조건:
  - 초기 손절: `ATR 2.0x`
  - 추적 손절: `ATR 4.5x` 기본
- 비용 가정:
  - 수수료 `0.04%`
  - 슬리피지 `0.05%`

## 종목별 기본 파라미터

| Symbol | Vol Mult | Trail ATR | Risk Per Trade | EMA Period | Loss Cap |
|---|---:|---:|---:|---:|---:|
| `TRUMP/USDT` | `2.5` | `4.5` | `0.02` | `100` | `-2%` |
| `ETH/USDT` | `2.0` | `4.5` | `0.02` | `200` | `-2%` |
| `BTC/USDT` | `2.0` | `4.5` | `0.01` | `200` | `-1%` |

## 현재 기본 해석
- `TRUMP/USDT`는 공격형 기본 전략이다.
- `ETH/USDT`는 중간 변동성 자산용 기본 전략이다.
- `BTC/USDT`는 보수형 기본 전략이다.
- BTC는 동일 구조를 유지하되 `Risk Per Trade`와 `Loss Cap`을 더 낮춰 방어적으로 운용한다.

## 최신 백테스트 기준 결과

| Symbol | Snapshot ID | Return | MDD | Trades | Final Capital |
|---|---|---:|---:|---:|---:|
| `TRUMP/USDT` | `bronze-trump_usdt-latest` | `+191.94%` | `15.58%` | `91` | `29,193.83 USDT` |
| `ETH/USDT` | `bronze-eth_usdt-latest` | `+181.71%` | `16.83%` | `112` | `28,171.15 USDT` |
| `BTC/USDT` | `bronze-btc_usdt-latest` | `-4.77%` | `20.68%` | `131` | `9,523.01 USDT` |

## 데이터 저장 원칙
- 시계열 저장소는 `timeseries-storage` 규칙을 따른다.
- 저장 구조는 `raw / bronze / silver / gold`를 유지한다.
- 현재 프로젝트 운용 모드는 `rolling latest`다.
- 즉, 종목별 최신 데이터셋 하나만 유지하고 이전 버전은 남기지 않는다.
- 최신 스냅샷 ID는 고정 이름을 사용한다.
  - `bronze-trump_usdt-latest`
  - `bronze-eth_usdt-latest`
  - `bronze-btc_usdt-latest`

## 마지막 봉 처리 원칙
- 마지막 봉은 미완성일 수 있으므로 다음 수집 시 다시 받아온다.
- 현재 구현은 마지막 구간을 겹쳐서 재수집한 뒤 동일 `timestamp`는 최신 응답으로 덮어쓴다.
- 따라서 최신 데이터는 누적 갱신되지만, 마지막 진행 중 봉은 다음 실행에서 수정될 수 있다.

## 실행 기준
- 새로운 종목 백테스트를 하지 않는 한 위 표를 기본 전략으로 간주한다.
- 차트와 성과 검증은 `scripts/backtest_snapshot.py` 기준으로 수행한다.
- 저장소 최신본을 사용하려면 종목별 `latest` snapshot ID를 사용한다.

## 변경 규칙
- 기본 전략을 바꾸려면 이 문서를 먼저 갱신한다.
- 파라미터 변경 시 최소 다음 항목을 함께 기록한다.
  - 변경 종목
  - 변경 파라미터
  - 손실 제한
  - 백테스트 기준 시각
  - 수익률 / MDD / 거래 수
