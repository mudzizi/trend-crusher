# Trading Session Log (2026-04-20) - Milestone: Race Condition & Double-Entry Fix (v13.1.13)

## ✅ 완료된 작업
1.  **중복 진입 방지 로직 (Race Condition Fix)**:
    -   체결 확인(`on_order_update`) 직후 SL 주문을 넣는 비동기 지연 시간(약 10~12초) 동안 새로운 진입이 발생하는 문제 해결.
    -   `is_processing_fill` 잠금 플래그와 즉각적인 `self.position` 업데이트를 통해 원자적(Atomic) 상태 전이 보장.
2.  **비동기 루프 안정화**:
    -   가격 업데이트(`on_mark_price_update`) 시 현재 포지션이 있거나 **진입 처리 중**인 경우 새로운 진입 체크를 즉시 차단하도록 개선.

## 🧪 검증 결과
-   **중복 진입 검증**: 체결 처리 중 발생하는 가격 변동에도 추가 주문이 나가지 않음을 확인.
-   **전체 75개 테스트 통과**: 잠금 로직 추가 후에도 기존 시뮬레이션 및 유닛 테스트 무결성 확인.

---

# Trading Session Log (2026-04-14) - Milestone: ADX Standard & Sniper Stabilization (v13.1.12)

## ✅ 완료된 작업
1.  **표준 ADX 로직 적용 (Wilder's Smoothing)**:
    -   단순 이동평균 기반의 ADX 계산을 **EMA 기반의 와일더(Wilder's) 방식**으로 전면 개편.
    -   가격 상승 시 ADX가 하락하던 현상을 해결하고, 트레이딩뷰 등 표준 플랫폼과 수치를 일치시킴.
2.  **스나이퍼(Sniper) 진입 안정화**:
    -   돌파 지점과 현재가 사이의 **0.03% 안전 마진(Safety Gap)** 도입.
    -   가격이 너무 가깝거나 이미 돌파한 경우 즉시 **시장가(MARKET)** 진입으로 자동 전환하여 "즉시 체결 에러" 원천 차단.
3.  **최고가 반영 우선순위 최적화**:
    -   라이브 봇 루프에서 `max_price_seen` 갱신을 손절가 계산보다 먼저 수행하도록 변경.
    -   현재 틱의 최고가가 실시간 손절가에 즉각 반영되도록 정밀도 향상.

## 🧪 검증 결과
-   **ADX 검증**: 가격 변동에 따른 추세 강도 반영 정상 작동 확인.
-   **스나이퍼 검증**: 돌파 직전/직후의 주문 에러 현상 해결 및 시장가 전환 확인.
-   **전체 75개 테스트 통과**: 기존 기능과의 완벽한 호환성 최종 확인.

---

# Trading Session Log (2026-04-14) - Milestone: Trailing SL Persistence & Resilient Recovery (v13.1.11)

## ✅ 완료된 작업
1.  **트레일링 스탑 상태 저장 버그 수정 (SL Persistence)**:
    -   `src/strategy.py`의 `check_exit_signal` 함수가 계산된 트레일링 가격을 `state['sl_price']`에 업데이트하지 않던 문제 해결.
    -   이제 수익 발생 시 봇의 메모리상 손절가가 실시간으로 상승하며, 거래소 주문 갱신(Sync)을 정상적으로 트리거함.

2.  **안전 장치 및 회복 탄력성(Resilience) 강화**:
    -   **Fail-safe Market Exit**: 새로운 트레일링 가격이 계산되었으나 아직 거래소 주문으로 동기화되기 전에 가격이 급락할 경우, 즉시 시장가(`execute_exit`)로 탈출하여 수익을 보호하는 로직 구현.
    -   **SL Auto-Recovery**: SL 주문이 거래소에서 사라지거나 생성이 실패할 경우, 즉시 종료하는 대신 텔레그램 알림 후 다음 루프에서 자동 재시도를 수행하여 수익 기회 보존.
    -   **Symbol Matching Fix**: 바이낸스의 `ETH/USDT:USDT` 형식을 정확히 지원하여, 포지션이 있는데도 없다고 오판하여 봇 상태를 초기화하던 버그 해결.

3.  **실시간 손절가 업데이트 알림 (Telegram Notification)**:
    -   거래소에 손절가 주문이 성공적으로 갱신되었을 때만 텔레그램으로 상세 알림을 전송하도록 개선.
    -   알림 내용에 새로운 손절가(New SL)와 현재 마크 가격(Mark Price)을 포함하여 투명성 확보.

4.  **전체 테스트 무결성 검증**:
    -   변경된 복구 로직에 맞춰 `tests/test_sl_robustness.py` 및 `tests/test_e2e_simulation.py` 수정.
    -   **전체 75개 테스트 100% 통과** 확인 (기존 기능과의 완벽한 호환성 입증).

## 🧪 검증 결과
-   **동기화 테스트**: 수익 발생 시 `state['sl_price']` 업데이트 및 거래소 주문 갱신 확인.
-   **복구 테스트**: SL 주문 누락 시 자동 재생성 및 사용자 알림 작동 확인.
-   **리그레션 테스트**: 전체 테스트 슈트 통과로 시스템 안정성 최종 확인.

---

# Trading Session Log (2026-04-06) - Milestone: Event-Driven Exit & Precision Sync (v13.1.10)

## ✅ 완료된 작업
1.  **ZeroDivisionError 완벽 차단**:
    -   Sniper 주문 체결 시 바이낸스 API가 가격을 `0`으로 반환하는 지연 현상에 대비하여 `last_price`를 백업으로 사용하는 가드 로직 도입.
    -   `get_detailed_status` 및 PnL 계산 시 `entry_price`가 0인 경우를 방어하는 안전 장치 전면 적용.

2.  **이벤트 기반 탈출(Event-Driven Exit) 아키텍처 개편**:
    -   봇이 직접 시장가 탈출 주문을 내지 않고, 거래소의 SL(StopLoss) 주문 체결 이벤트(`FILLED`)를 WebSocket으로 수신하여 처리하도록 개선.
    -   중복 주문 및 경쟁 상태(Race Condition)에 의한 에러를 원천 차단하고 거래소 엔진의 처리를 우선 신뢰하도록 변경.

3.  **거래소 기반 정밀 동기화 (Precision Position Sync)**:
    -   `sync_all_orders` 메서드를 강화하여 `fetch_positions` API를 통해 실제 거래소의 평단가(`entryPrice`)와 계약 수(`contracts`)를 직접 조회.
    -   봇의 로컬 상태와 거래소 장부 데이터가 100% 일치하도록 강제 보정(Repair)하는 로직 구현.

4.  **심볼 필터링 및 복구 도구 추가**:
    -   대시보드에서 현재 `SYMBOLS_LIST`에 포함된 활성 심볼만 표시하도록 필터링 로직 개선.
    -   상태 불일치 시 수동으로 DB를 초기화할 수 있는 `scripts/emergency_recovery.py` 유틸리티 제작.

## 🧪 검증 결과
-   **75/75 테스트 통과**: E2E 시뮬레이션 및 신규 `test_sl_robustness.py`를 포함한 전체 테스트 세트가 100% 성공.
-   바이낸스 실제 체결 지연 상황을 가정한 Mock 테스트 환경에서 무결성 입증.

---

# Trading Session Log (2026-04-02) - Milestone: Binance Trigger Order Bug Fix (v13.1.8)

## ✅ 완료된 작업
1.  **바이낸스 조건부 주문(Trigger Orders) 연동 버그 수정**:
    -   바이낸스 선물 거래소에서 `STOP_MARKET` 주문이 일반 조회 API로는 확인되지 않던 문제 해결.
    -   `fetch_trigger_order`, `cancel_trigger_order` 메서드를 신설하여 `params={'trigger': True}` 옵션 적용.
    -   스나이퍼 주문 체결 확인 및 손절 주문 취소 시의 안정성 확보.
2.  **포지션 종료 안전 장치 강화**:
    -   `create_reduce_only_market_order`를 통해 모든 종료 시장가 주문에 `reduceOnly: True` 옵션 강제 적용.
    -   의도치 않은 신규 포지션 오픈(Flip) 방지.
3.  **검증 자동화 업데이트**:
    -   변경된 주문 인터페이스에 맞춰 `tests/test_live_sync_pnl.py`의 `force_exit` 로직 검증 코드 수정.

## 🧪 검증 결과
-   전체 테스트(72개) 100% 통과 확인.
-   바이낸스 테스트넷/라이브 환경에서 `STOP_MARKET` 주문의 동기화 무결성 확보 예상.

---

# Trading Session Log (2026-04-02) - Milestone: EMA Visualization Fix (v13.1.7)

## ✅ 완료된 작업
1.  **실시간 EMA 데이터 저장 및 연동**:
    -   `live_indicators` 테이블에 `ema_value` 컬럼 추가 (자동 마이그레이션 포함).
    -   `scripts/live_bot_async.py`가 실시간 지표를 기록할 때 실제 EMA 100/200 값을 함께 저장하도록 수정.
    -   `scripts/dashboard.py`에서 실시간 차트의 마지막 점을 그릴 때 근사치 대신 DB의 실제 EMA 값을 사용하도록 수정.
2.  **버전 업데이트**:
    -   시각적 오류 수정 및 DB 스키마 변경 사항을 포함하여 `v13.1.7`로 업데이트.

## 🧪 검증 결과
-   대시보드 차트에서 EMA(황색 점선)가 마지막 "Now" 지점에서 급격히 꺾이지 않고, 이전 흐름을 유지하며 매끄럽게 연결됨을 확인.
-   `trades.db`의 `live_indicators` 테이블에 `ema_value` 데이터가 정상적으로 쌓이는 것 확인.

---

# Trading Session Log (2026-04-02) - Milestone: Static Donchian Breakout Optimization (v13.1.6)

## ✅ 완료된 작업
1.  **Donchian Channel 로직 최적화 (Static Breakout)**:
    -   `src/indicators.py`의 `calculate_donchian` 함수에 `shift(1)`을 적용.
    -   현재 진행 중인 봉의 고가/저가가 밴드 계산에 포함되어 밴드가 계속 도망가는(Trailing) 현상 해결.
    -   전봉 마감 기준의 정적인 상/하단 밴드를 제공함으로써 Sniper 모드 및 돌파 매매의 체결 가능성과 기술적 정합성 향상.

## 🧪 검증 결과
-   이론적으로 가격이 밴드를 터치하는 지점이 고정됨에 따라 Sniper(Maker) 주문이 정확한 지점에서 대기할 수 있음을 확인.
-   대시보드 차트에서 밴드가 현재 가격에 따라 실시간으로 변하지 않고 정적인 기준선으로 유지됨을 확인.

---

# Trading Session Log (2026-04-02) - Milestone: Persistence & Resilience Fix (v13.1.5)

## ✅ 완료된 작업
1.  **상태 저장 로직 수정 (Persistence Fix)**:
    -   `DBManager.save_bot_state`가 `sniper_order_id`와 `retest_order_id`를 받도록 메서드 시그니처 수정.
    -   기존에 9개 인자를 받던 메서드에 2개를 추가하여 `persist_state()` 호출 시 발생하던 `TypeError` 해결.
2.  **주문 동기화 안정성 강화 (Resilience)**:
    -   `check_sniper_fill` 및 `check_retest_fill`에서 `ccxt.OrderNotFound` (Binance -2013) 예외 처리 추가.
    -   거래소에 존재하지 않는 주문 ID를 계속 폴링하며 에러를 뿜는 대신, 상태를 즉시 클리어하고 DB를 업데이트하도록 개선.

## 🧪 검증 결과
-   로그에서 발생하던 `takes 9 positional arguments but 11 were given` 에러 제거 확인.
-   바이낸스 `-2013 (Order does not exist)` 발생 시 무한 재시도가 아닌 상태 클리어 및 로깅 정상 작동 확인.

---

# Trading Session Log (2026-04-01) - Milestone: Real-time Interactive Dashboard (v13.1.4)

## ✅ 완료된 작업
1.  **실시간 차트 데이터 병합 (Live Data Injection)**:
    -   `scripts/dashboard.py`를 개선하여 `history_1h`(과거 마감봉) 데이터 끝에 `live_indicators`(현재 진행 중인 봉) 데이터를 즉시 추가하도록 수정.
    -   사용자가 1시간이 지날 때까지 기다리지 않고도 현재 가격과 지표 추세를 차트에서 바로 확인할 수 있도록 개선.
2.  **시간 라벨링 최적화**:
    -   실시간 데이터 포인트에 "HH:MM (Now)" 라벨을 부여하여 마감된 데이터와 시각적으로 구분.
3.  **지표 연동 무결성 확보**:
    -   Price, Donchian Channels, ADX, Volume 비율 등을 실시간 데이터 포인트에 정확히 매핑.

## 🧪 검증 결과
-   대시보드 접속 시 08:00 마감봉 이후에 현재 시각(09:50 등)의 가격이 차트에 실시간으로 이어져 출력됨을 확인.
-   지표(Upper/Lower) 또한 현재 봇이 감시 중인 돌파 기준선에 맞게 동적으로 표시됨.

---

# Trading Session Log (2026-04-01) - Milestone: Dashboard Timezone & Logging Fix (v13.1.3)

## ✅ 완료된 작업
1.  **대시보드 한국 시간(KST) 전환**:
    -   `scripts/dashboard.py`를 수정하여 DB에서 가져온 UTC 타임스탬프에 +9시간을 더해 KST로 표시하도록 변경.
    -   개별 심볼 차트 및 하단 포트폴리오 자산 차트 모두에 적용 완료.
2.  **실시간 차트 데이터 로깅 주기 수정**:
    -   `scripts/live_bot_async.py`에서 기존 4시간(`trend_tf`)마다 저장되던 로직을 1시간(`signal_tf`)마다 저장되도록 변경.
    -   이제 매 정시(KST 기준)마다 차트 데이터가 정상적으로 쌓이게 됨.
3.  **포트폴리오 가치 표시 로직 확인**:
    -   `equity` 테이블이 비어있을 경우 `config.yaml`의 `SEED` 값을 읽어오는 구조 확인 및 `.env` 파일의 우선순위 재확인.

## 🧪 검증 결과
-   `scripts/dashboard.py` 실행 시 기존 UTC 15:00 데이터가 KST 00:00으로 정상 표시됨을 확인.
-   `live_bot_async.py`의 `kline['x']` 조건이 `signal_tf`와 일치할 때 로깅 로직이 실행되도록 수정됨.

---

# Trading Session Log (2026-03-31) - Milestone: Macro Strategy Visualization & UX Fix (v13.1.1)

## ✅ 완료된 작업
1.  **거시적 지표 시각화 (Hourly Charting)**:
    -   `history_1h` 테이블 및 48시간 자동 백필(Backfill) 로직 구현.
    -   Y축 멀티 축 및 인디케이터 통합형 고성능 차트 엔진 도입.

2.  **대시보드 UX 개선**:
    -   심볼 알파벳 순서 정렬을 통해 대시보드 리스트 위치 고정.
    -   정확한 컬럼 매핑(`ema_h`, `upper`, `lower`)으로 데이터 출력 무결성 확보.

3.  **최종 시스템 안정화**:
    -   `db_manager.py` 문법 오류 수정 및 전체 테스트 71개 통과 완료.

---

# Trading Session Log (2026-03-31) - Milestone: Flexible Symbol Matching & AWS Readiness (v12.9.2)

## ✅ 완료된 작업
1.  **심볼 매칭 유연성 확보**:
    -   `ws_loop`에서 `ETHUSDT` 및 `ETH/USDT` 등 다양한 심볼 표기 방식을 동시에 지원하도록 수정.
    -   특정 코인(ETH)이 대시보드에 나타나지 않던 매칭 오류 해결.

2.  **초기 상태 기록 강제**:
    -   봇 초기화 즉시 DB에 현재 상태를 기록하여 대시보드 로딩 시 모든 심볼이 즉시 나타나도록 개선.

3.  **패치 버전 업데이트**:
    -   버전을 `12.9.2`로 상향하고 전체 코드 업로드 준비 완료.

---

# Trading Session Log (2026-03-31) - Milestone: Dashboard Indicator Fix (v12.9.1)

## ✅ 완료된 작업
1.  **대시보드 실시간 지표 복구**:
    -   `scripts/live_bot_async.py`의 `ws_loop`에 `markPriceUpdate` 이벤트 핸들러를 추가하여 DB의 `live_status`가 주기적으로 갱신되도록 수정.
    -   대시보드에서 각 심볼의 보조지표 상태가 정상적으로 시각화됨을 확인.

2.  **패치 버전 업데이트**:
    -   버전을 `12.9.1`로 상향하고 `CHANGELOG.md` 및 설정 파일 갱신.

---

# Trading Session Log (2026-03-31) - Milestone: WebSocket Resilience & Account Logging (v12.9.0)

## ✅ 완료된 작업
1.  **공식 Binance Connector 도입**:
    -   `binance-futures-connector` 라이브러리를 활용하여 WebSocket 연결의 신뢰성을 기업 수준으로 격상.
    -   서버 Ping/Pong 자동 대응 및 24시간 세션 유지 로직 표준화.

2.  **ListenKey 회복 탄력성(Resilience) 강화**:
    -   `listenKey` 연장 실패 시 즉시 새 키를 재발급받고 유저 데이터 스트림을 갱신하는 자동 복구 로직 구현.

3.  **Gap-Filling 주문 동기화**:
    -   WS 재연결(`WS_RECONNECTED`) 발생 시 REST API를 통해 모든 활성 주문의 상태를 강제로 동기화하여 체결 누락을 원천 차단.

4.  **계정 통합 주문 로깅**:
    -   `log/account_orders.log`를 신설하여 봇이 감시하지 않는 심볼을 포함한 계정 내 모든 주문 이벤트를 실시간 기록.

5.  **버전 업그레이드**:
    -   시스템 버전을 `12.9.0`으로 상향하고 `CHANGELOG.md` 및 설정 파일 업데이트 완료.

---

# Trading Session Log (2026-03-31) - Milestone: Enhanced Transparency & Reliability (v12.8.4)

## ✅ 완료된 작업
1.  **상세 `/status` 리포트 시스템 구축**:
    -   단순 포지션 여부 출력을 넘어, 현재가, EMA 기준선, 채널 밴드, 지표 달성도(Vol/ADX), 진입 임박도(Prox %)를 포함한 종합 리포트 구현.
    -   사용자가 봇의 판단 근거를 실시간으로 완벽하게 파악 가능하도록 개선.

2.  **긴급 청산 알림 복구**:
    -   리팩토링 과정에서 누락되었던 `force_exit` 시 텔레그램 알림 로직 재이식.
    -   비상 상황 대응 결과에 대한 가시성 확보.

3.  **코드 무결성 및 런타임 안정화**:
    -   `live_bot_async.py` 파일 끝의 중복 파편 제거 및 들여쓰기 오류(`IndentationError`) 해결.
    -   지표 계산 루프의 `is_live` 변수 정의 오류 수정 및 코드 클린업.

4.  **시스템 최종 검증**:
    -   전체 71개 테스트 케이스 100% 통과 재확인.
    -   Dry Run 환경에서의 실제 구동 및 웹소켓 연결 안정성 확인.

## 🧪 검증 결과
-   **통합 테스트**: `pytest` 결과 전 항목 합격.
-   **런타임 체크**: `scripts/live_bot_async.py` 초기화 및 스트리밍 엔진 정상 작동 확인.

---

# Trading Session Log (2026-03-31) - Milestone: Advanced WebSocket Engine (v12.8.3)

## ✅ 완료된 작업
1.  **차세대 웹소켓 엔진 (`stream()`) 도입**:
    -   `BinanceWebSocketManager`를 비동기 제너레이터 구조로 리팩토링.
    -   `live_bot_async.py`의 메인 루프에서 `async for msg in ws_manager.stream()` 구문을 통해 지연 없는 실시간 데이터 처리 가능.

2.  **개인 스트림(User Data) 자동 관리**:
    -   바이낸스 `listenKey` 생성, URL 병합, 30분 주기 갱신(Keep-alive) 로직을 매니저 내부로 캡슐화.
    -   별도의 설정 없이도 `ORDER_TRADE_UPDATE` 이력을 실시간으로 수신하여 Sniper/Retest 체결 즉시 감지.

3.  **하위 호환성 및 안정성 확보**:
    -   기존 테스트 슈트가 의존하는 `get_next_message()` 메서드를 복구하여 회귀 테스트 100% 통과 유지.
    -   `EXCHANGE` 설정 누락 시 발생하는 `KeyError` 방지를 위해 기본값(`binance`) 강제 적용.

4.  **시스템 검증**:
    -   `tests/test_websocket.py`를 포함한 전체 71개 테스트 케이스 통과 확인.

## 🧪 검증 결과
-   **통합 테스트**: `pytest` 결과 모든 항목 정상 (v12.8.3 무결성 확인).
-   **실전 로그**: 웹소켓 연결 및 `listenKey` 갱신 로그 정상 작동 확인.

---

# Trading Session Log (2026-03-30) - Milestone: Ambush Persistence & Reliability (v12.8.2)

## ✅ 완료된 작업
1.  **매복 주문 영구 추적 (Ambush Persistence)**:
    -   `bot_state` DB 테이블에 `sniper_order_id`, `retest_order_id` 컬럼 추가.
    -   봇 재시작 시 대기 중인 매복 주문을 자동 복구하여 체결 누락 원천 차단.

2.  **30초 주기 상태 폴링 (Redundant Polling)**:
    -   웹소켓 누락에 대비하여 30초마다 거래소 API를 통해 주문 상태를 확인하는 백업 로직 가동.
    -   네트워크 불안정 시에도 최대 30초 이내에 포지션 진입 자동 감지.

3.  **전역 주문 진단 로깅 (Diagnostic Logging)**:
    -   웹소켓으로 들어오는 모든 주문 업데이트(ID, 상태, 수량, 가격)를 상세 로그에 기록.
    -   매칭되지 않는 주문이나 무시된 이벤트까지 투명하게 추적 가능.

4.  **긴급 청산 로직 보완 (Force Exit PnL)**:
    -   `/close_all` 등 긴급 청산 시에도 실제 체결가를 반영하여 DB에 매매 기록(`log_trade_close`)을 남기도록 개선.
    -   긴급 상황에서도 수익률 통계의 연속성 유지.

## 🧪 검증 결과
-   **통합 테스트**: 71개 테스트 케이스 전원 통과 (v12.8.2 안정성 검증 완료).
-   **실전 파리티**: `is_live` 변수 참조 오류 해결 및 코드 클린업 완료.

---

# Trading Session Log (2026-03-29) - Milestone: Precision Sniper & Dashboard Sync (v12.8.1)

## ✅ 완료된 작업
1.  **Sniper 모드 `STOP_MARKET` 고도화**:
    -   기존 `LIMIT` 주문 방식의 맹점(현재가보다 높은 Buy Limit 시 즉시 Taker 체결)을 해결하기 위해 `STOP_MARKET` 주문으로 전면 교체.
    -   이로써 돌파 지점(`target_price`)을 실제로 터치할 때만 주문이 실행되어 불필요한 슬리피지 및 조기 체결 방지.

2.  **체결 평단가(`ap`) 정밀 반영**:
    -   웹소켓 `on_order_update`에서 마지막 체결가(`L`) 대신 전체 평균 체결가(`ap`)를 우선 참조하도록 수정.
    -   `STOP_MARKET` 및 `MARKET` 체결 시 발생하는 다중 체결 상황에서도 대시보드 평단가를 정확히 일치시킴.

3.  **대시보드 실시간 동기화 보완**:
    -   웹소켓으로 `FILLED` 이벤트 수신 시 즉시 `_on_fill_success`를 통해 `persist_state`를 호출하여 DB 상태를 강제 갱신.
    -   봇이 체결되었음에도 대시보드에 표시되지 않던 데이터 싱크 문제를 원천적으로 해결.

4.  **시스템 검증 (Zero Regression)**:
    -   `STOP_MARKET` 파라미터(stopPrice 등) 검증 로직을 `tests/test_sniper_logic.py`에 반영.
    -   **71개 전체 테스트 케이스 100% Pass** 확인.

## 🧪 검증 결과
-   **유닛 테스트**: `pytest tests/` 결과 모든 항목 통과.
-   **동작 검증**: Mock Exchange 호출 인자 분석을 통해 `STOP_MARKET` 파라미터의 정확한 전달 확인.

---

# Trading Session Log (2026-03-28) - Milestone: ADX Transparency & Dashboard UI (v12.9.0)

## ✅ 완료된 작업
1.  **ADX 실시간 투명성 확보 (ADX Transparency)**:
    -   대시보드에서 ADX 값이 항상 100%로 표시되던 문제 해결 (기존에는 목표치 대비 비율만 표시).
    -   `live_indicators` 테이블에 `adx_value` 컬럼을 추가하여 실제 ADX 수치를 저장하고 대시보드에 전달.
    -   UI 수정: `ADX Strength` 섹션에 실제 수치와 목표 대비 비율을 병기 (예: **32.5** / 100%).

2.  **데이터베이스 스키마 마이그레이션**:
    -   `src/db_manager.py`에 자동 컬럼 추가 로직(`ALTER TABLE`)을 반영하여 기존 데이터 유실 없이 `adx_value` 필드 확장.

3.  **봇 및 대시보드 연동 최적화**:
    -   `scripts/live_bot_async.py`에서 계산된 실제 ADX 값을 DB에 실시간 기록하도록 수정.
    -   `scripts/dashboard.py`에서 신규 필드를 읽어 프론트엔드로 전달하는 데이터 파이프라인 연결.

## 🧪 검증 결과
-   **DB 마이그레이션 테스트**: `test_db_migration.py`를 통해 신규 컬럼 생성 및 데이터 입출력 정상 작동 확인.
-   **대시보드 통합 테스트**: `tests/test_dashboard.py`를 수정된 UI 스펙에 맞춰 업데이트하고 100% 통과 확인.
-   **회귀 테스트**: 전체 테스트 슈트 실행을 통해 기존 기능 영향 없음 확인.

---

# Trading Session Log (2026-03-25) - Milestone: Security Hardening & Dashboard Fixes (v12.8.0)

## ✅ 완료된 작업
1.  **대시보드 보안 강화 (Security Hardening)**:
    -   `scripts/dashboard.py`의 Flask 호스트를 `127.0.0.1`로 제한하여 외부 접근 차단.
    -   RCE 위험이 있는 `debug=True` 모드를 비활성화하여 안정성 및 보안성 확보.
    -   **Path Traversal 방어**: 리포트 파일 접근 시 절대 경로 정규화(`abspath`) 및 상위 디렉토리 접근 차단 로직 적용.

2.  **포트폴리오 자산 표시 수정 (UI/UX Fix)**:
    -   대시보드 상단의 'PORTFOLIO VALUE'가 초기 SEED와 누적 PnL을 합산한 실제 총 자산을 정확히 반영하도록 수정.
    -   자산 차트 데이터가 개별 심볼 데이터와 섞이지 않도록 `symbol='TOTAL'` 필터링 적용.
    -   `PortfolioManagerAsync` 및 `DBManager` 연동을 통해 실시간 자산 정합성 확보.

## 🧪 검증 결과
-   **보안 테스트**: `../` 등을 이용한 경로 탐색 시도 시 `403 Access Denied` 정상 반환 확인.
-   **정합성 테스트**: 전체 테스트(71개) 통과 및 대시보드 데이터 일치 확인.

---

# Trading Session Log (2026-03-25) - Milestone: Mega-Turbo Parallel Optimizer (v12.7.0)

## ✅ 완료된 작업
1.  **작업 단위(Task-level) 병렬화 도입**:
    -   `scripts/mega_optimizer_v2.py`를 리팩토링하여 '심볼 단위' 병렬화에서 '파라미터 조합(Task) 단위' 병렬화로 전환.
    -   CPU 코어 수에 관계없이 모든 코어가 항상 100% 가동되도록 부하 분산 최적화.
    -   `ProcessPoolExecutor`의 `chunksize`를 조정하여 수만 개의 작은 작업을 효율적으로 처리.

2.  **최적화 엔진 통합 (SSOT)**:
    -   NumPy, Numba, Jump 최적화가 모두 적용된 `run_streaming_backtest`를 최적화 도구의 메인 엔진으로 채택.
    -   이전의 파편화된 백테스트 메서드들을 통합하여 결과의 신뢰성과 속도를 동시에 확보.

## 🧪 검증 결과
-   **성능**: 10개 심볼, 수천 개 조합 최적화 시 기존 대비 연산 속도가 하드웨어 코어 수에 비례하여 선형적으로 향상됨을 확인.
-   **안정성**: 병렬 프로세스 간 데이터 간섭 방지 및 Telegram 리포트 정상 발송 확인.

---

# Trading Session Log (2026-03-25) - Milestone: Vectorized Jump Exit Engine (v12.6.0)

## ✅ 완료된 작업
1.  **Vectorized Exit Search (Jump 최적화)**:
    -   포지션 진입 후 청산 시점까지의 수천 건의 1분봉 루프를 단 한 번의 JIT 가속 함수(`numba_find_first_exit`) 호출로 대체.
    -   `while` 루프 내에서 청산 인덱스로 즉시 점프하여 백테스트 성능을 극대화.

2.  **자산 곡선 무결성 복구 (Equity Curve Recovery)**:
    -   점프 구간 동안 생략되는 일일 자산 기록(`equity_curve`)을 청산 전/후 자본 상태를 정밀하게 구분하여 복구.
    -   최적화 전/후의 수익률뿐만 아니라 **Max Drawdown(37.76%)까지 100% 동일하게 일치**시킴으로써 무결성 검증 완료.

## 🧪 검증 결과
-   **성능**: 포지션 유지 기간이 길수록(Long-term trades) 성능 향상 폭이 기하급수적으로 증가.
-   **정합성**: TRUMP/USDT 365일 시뮬레이션 결과(Return: +2201.04%, MDD: 37.76%) 완벽 일치.

---

# Trading Session Log (2026-03-25) - Milestone: Numba JIT Accelerated Engine (v12.5.0)

## ✅ 완료된 작업
1.  **Numba JIT 트레이딩 로직 최적화 (JIT Engine)**:
    -   `src/strategy.py`의 핵심 판단 로직(`check_entry_signal`, `check_exit_signal`)을 Numba `@njit` 기반의 고성능 함수로 분리.
    -   Python 인터프리터 오버헤드를 제거하고 C 수준의 기계어 컴파일 실행을 통해 백테스트 루프 처리 성능을 극대화.
    -   가변적인 `adaptive_steps` 설정을 JIT 함수가 처리할 수 있도록 NumPy 2D 배열 인터페이스로 변환하여 전달.

2.  **결과 무결성 재검증 (Double Invariant Check)**:
    -   v12.4.0 (NumPy Turbo) 결과와 v12.5.0 (Numba JIT) 결과를 1분봉 단위로 비교하여 **단 하나의 거래 오차도 없음**을 최종 확인.
    -   TRUMP/USDT 365일 시뮬레이션 결과: 수익률 **+2201.04%**, MDD **37.76%** 완벽 일치.

## 🧪 검증 결과
-   **성능 향상**: 루프 내 조건문 처리 속도가 비약적으로 향상되어, 복잡한 파라미터 최적화(Grid Search) 시 전체 소요 시간을 획기적으로 단축 가능.
-   **안정성**: `numba` 라이브러리 설치 및 컴파일 환경 검증 완료.

---

# Trading Session Log (2026-03-25) - Milestone: NumPy Turbo Backtest Engine (v12.4.0)

## ✅ 완료된 작업
1.  **NumPy 기반 백테스트 가속화 (Turbo Engine)**:
    -   `src/strategy.py`의 `run_streaming_backtest` 루프를 NumPy 원시 배열 연산으로 전면 리팩토링.
    -   루프 내부의 Pandas `loc/iloc` 인덱싱 오버헤드를 제거하고, 시간-인덱스 사전 매핑(Searchsorted Lookup) 방식을 도입.
    -   객체 속성 접근 대신 로컬 변수 캐싱을 통해 Python 루프 속도 최적화.

2.  **결과 무결성 검증 (Invariant Verification)**:
    -   `scripts/run_realistic_simulation.py`를 활용하여 최적화 전/후의 매매 이력(Trade Log) 및 수익률(Return)이 100% 일치함을 수학적으로 검증 완료 (+2026.42% @ pnl_pct=10.0 기준).
    -   소수점 오차나 로직 변경 없이 순수하게 실행 속도만 향상시킴.

## 🧪 검증 결과
-   **성능 향상**: 대량의 1분봉 데이터(52만 라인) 시뮬레이션 시 기존 대비 약 5~8배 이상의 처리 속도 향상 확인.
-   **정합성**: TRUMP/USDT 365일 시뮬레이션 결과값 완벽 일치 확인.

---

# Trading Session Log (2026-03-25) - Milestone: Safe Order Response Handling (v12.3.0)

## ✅ 완료된 작업
1.  **전역적 주문 응답 방어 코드 (NoneType Guard Expansion)**:
    -   `scripts/live_bot_async.py`와 `scripts/live_bot_multi.py`의 모든 `order.get()` 호출 지점에 대해 `order` 객체가 `None`이거나 딕셔너리가 아닌 경우를 대비한 방어 로직 적용.
    -   중첩된 `fee` 필드 접근 시 `(order.get('fee') or {}).get('cost')` 패턴을 사용하여 `NoneType` 에러 원천 차단.
    -   거래소 API 응답이 불안정할 경우(Timeout 등)에도 `last_price` 및 기존 `quantity`를 사용하여 안전하게 상태를 전이하도록 폴백 메커니즘 구축.

2.  **전략 엔진(SSOT) 및 WebSocket 최적화 통합**:
    *   `src/strategy.py`와 `src/indicators.py`의 실시간 증분 계산 로직 및 Donchian 채널 정합성 개선 사항 반영.
    *   `src/websocket_manager.py`의 유저 데이터 스트림(Private WS) 지원 및 재연결 지수 백오프 로직 공식 적용.

## 🧪 검증 결과
-   **구문 검사 완료**: `python3 -m py_compile`을 통해 수정된 모든 스크립트의 문법적 무결성 확인.
-   **단위 테스트 업데이트**: `tests/test_live_sync_pnl.py` 및 `tests/test_sniper_logic.py`에 새로운 방어 로직(Margin Guard 등)에 대응하는 Mock 데이터 보강 완료.

---

# Trading Session Log (2026-03-25) - Milestone: Margin Safety Guard & Multi-Currency (v12.2.0)

## ✅ 완료된 작업
1.  **가용 증거금 실시간 검증 (Margin Safety Guard)**:
    -   `execute_entry`, `manage_retest_ambush`, `manage_sniper_ambush` 직전 거래소의 `fetch_balance`를 호출하여 실시간 가용 잔고 확인.
    -   심볼로부터 정산 통화(USDT 또는 USDC)를 동적으로 추출하여 해당 통화의 잔고를 체크하도록 개선.
    -   설정된 레버리지를 고려하여 필요 증거금을 계산하고, 잔고 초과 시 수량을 가용 범위(95%) 내로 자동 하향 조정(Downsizing).
    -   `Insufficient Margin` 에러로 인한 주문 거부를 원천 방지하고 주문 성공률 극대화.

2.  **멀티 커런시(USDT/USDC) 완벽 지원**:
    -   정산 통화에 관계없이 실시간 잔고 기반의 리스크 관리가 가능하도록 범용성 확보.

## 🧪 검증 결과
-   `tests/test_risk_safety.py` 수행 완료 (성공)
-   USDT/USDC 각각의 잔고 부족 상황 시뮬레이션 시 수량 하향 조정 및 경고 로그 정상 출력 확인.

---

# Trading Session Log (2026-03-25) - Milestone: Anti-Drift Sync & Manual Control (v12.1.0)

## ✅ 완료된 작업
1.  **양방향 상태 동기화 (Anti-Drift Sync) 강화**:
    -   `sync_db_with_exchange`를 고도화하여 DB와 봇의 메모리 상태를 거래소의 실제 포지션과 양방향으로 대조.
    -   누락된 포지션 복구, 유령 포지션 제거, 수량 불일치 교정 로직 추가.
    -   1시간마다 백그라운드에서 자동으로 전체 동기화 수행 (`auto_sync_loop`).

2.  **수동 동기화 명령어 도입 (`/sync`)**:
    -   텔레그램 채팅창에서 사용자가 `/sync` 명령어를 입력하면 즉시 전체 심볼에 대해 거래소 대조 수행.
    -   동기화 결과(복구/제거 내역)를 텔레그램 리포트로 즉시 전송.
    -   메인 키보드 메뉴에 `/sync` 버튼 배치하여 접근성 개선.

## 🧪 검증 결과
-   `tests/test_live_optimizations.py`를 통한 수동 호출 시뮬레이션 완료.
-   기존 71개 테스트 케이스의 영향 없음 확인.

---

# Trading Session Log (2026-03-25) - Milestone: High-Performance Live Optimization (v12.0.0)

## ✅ 완료된 작업
1.  **실시간 User Data Stream (WebSocket) 통합**:
    -   바이낸스 `listenKey` 기반의 전용 WebSocket 스트림을 구축하여 체결 리포트(`ORDER_TRADE_UPDATE`)를 실시간으로 수신.
    -   기존의 API 폴링 방식을 대체하여 Sniper/Retest/StopLoss 체결 처리를 즉각적으로 수행하고 Rate Limit 소모를 최소화.

2.  **지표 증분 계산 (Incremental Calculation) 최적화**:
    -   실시간 트레이딩 모드(`is_live=True`)에서 전체 데이터가 아닌 최근 윈도우(Tail) 데이터만 슬라이싱하여 지표를 계산하도록 엔진 수정.
    -   Pandas 연산 부하를 80% 이상 절감하면서도 EMA/ADX 지표의 정합성을 유지 (유닛 테스트 완료).

3.  **성능 스로틀링 (Performance Throttling)**:
    -   DB 기록 및 대시보드 상태 업데이트 주기를 5초로 스로틀링하여 SQLite 쓰기 부하 경감.
    -   지표 재계산 주기를 10초로 제한하여 초당 수십 건의 마크 가격 업데이트 시에도 CPU 안정성 확보.

4.  **거래소 연동 트레일링 SL (SL Exchange Sync)**:
    -   내부 트레일링 스탑 가격이 유의미하게 이동(0.05% 이상)할 경우 거래소의 `STOP_MARKET` 주문을 자동으로 갱신(Cancel & Replace)하는 동기화 로직 구현.
    -   급격한 변동성 상황에서 로컬 봇의 지연 없이 거래소 엔진에서 즉시 손절이 작동하도록 안전 장치 강화.

## 🧪 검증 결과
-   **전체 테스트 수행 완료 (71/71 Pass)**:
    -   `pytest tests/` 결과 모든 유닛/통합 테스트 통과 확인.
-   `tests/test_live_optimizations.py` 수행 완료 (4/4 Pass)
    -   증분 계산 오차 범위 검증 완료.
    -   WebSocket 체결 메시지 처리 및 상태 전이 검증 완료.
    -   스로틀링 및 SL 동기화 임계치 작동 확인 완료.

---

# Trading Session Log (2026-03-25) - Milestone: Self-Healing & Startup Sync (v11.9.10)

## ✅ 완료된 작업
1.  **부팅 시 자동 데이터 동기화 (Startup Sync)**:
    -   봇 시작 시 DB의 'OPEN' 포지션과 거래소의 실제 잔고를 전수 대조하는 `sync_db_with_exchange` 도입.
    -   거래소에는 없으나 DB에만 남은 "유령 포지션"을 자동으로 탐지하여 `CLOSED` 처리하고 대시보드 정합성 확보.

2.  **청산 무결성 강화 (Exit Verification)**:
    -   시장가 청산 주문 직후 거래소 API로 실제 잔고가 0이 되었는지 실시간 확인하는 로직 강화 (v11.9.9).
    -   청산 실패 시 남은 수량만큼 즉시 재시도하여 포지션 방치 원천 차단.

3.  **API 안정성 패치 (NoneType Guard)**:
    -   거래소 응답이 유효하지 않을 때(None) 발생하던 `'NoneType' object has no attribute 'get'` 에러에 대한 전역 방어 코드 적용 (v11.9.8).
    -   비정상적 응답 시에도 `last_price` 기반의 안전한 상태 정리를 통해 무한 루프 크래시 방지.

4.  **문서 및 형상 관리**:
    -   `src/config.py`, `README.md`, `CHANGELOG.md` 버전을 **v11.9.10**으로 동기화 완료.

---

# Trading Session Log (2026-03-23) - Milestone: Turbo Optimization & Financial Parity (v11.9.7)

## ✅ 완료된 작업
1.  **엔진 성능 비약적 향상 (NumPy Turbo)**:
    -   `src/strategy.py`의 메인 루프를 NumPy 벡터화 기반으로 재설계하여 백테스트 속도를 약 5배 단축.
    -   타임스탬프 매칭 로직을 `datetime64[m]`으로 표준화하여 1분봉과 1시간봉 지표 간의 매칭 실패(Trades 0건 발생 문제)를 완벽히 해결.

2.  **최적화 도구 고도화 (Smart Overnight Optimizer)**:
    -   **스마트 이어하기**: 특정 폴더가 아닌 `reports/` 하위의 모든 CSV를 스캔하여 중복 계산을 전역적으로 차단.
    -   **실시간 모니터링**: 50개 조합마다 현재 시간, 진행률(%), 경과 시간(Elapsed Time)을 출력하여 밤샘 작업의 가시성 확보.
    -   **베스트 요약**: 분기별 최적 조합만 따로 모은 `best_summary.csv` 자동 생성 기능 추가.

3.  **실전적 회계 로직 적용 (Fee Differentiation)**:
    -   수수료 체계를 Maker(0.02%)와 Taker(0.05%)로 분리하여 지정가 매복(Sniper/Retest)의 비용 절감 효과를 백테스트에 100% 반영.
    -   데이터가 짧은 종목(XAU 등)을 위해 EMA 기간을 데이터 양에 맞춰 유연하게 줄이는 **Adaptive Indicator** 로직 도입.

4.  **Zero Regression 검증**:
    -   인터페이스 변경에 따른 기존 테스트 코드(`test_hysteresis_persistence`, `test_optimizer` 등)를 전면 수정 및 최신화.
    -   **67개 전체 테스트 스위트 100% Pass** 확인 완료.

---

# Trading Session Log (2026-03-23) - Milestone: Dashboard V4.5 Control Center (v11.9.5)

## ✅ 완료된 작업
1.  **실시간 전략 관제 시스템 구축**:
    *   **개별 지표 근접도 시각화**: 거래량(Volume), 추세(ADX), 가격 근접도(Proximity)를 진행 바(%)로 표시하여 진입 근거를 투명하게 공개.
    *   **종합 신호 점수(0~100)**: 지표별 가중치를 적용한 통합 점수 시스템 도입. 80점 이상 시 시각적 강조로 진입 임박 알림.
    *   **DB 기반 브릿지**: 봇(`live_bot_async`)이 계산한 지표를 DB(`live_indicators` 테이블)를 통해 대시보드로 즉시 전달하는 아키텍처 구현.

2.  **UI/UX 전면 개편**:
    *   **카드 기반 레이아웃**: 코인별 전략 상태를 독립적인 카드로 배치하여 가독성 향상.
    *   **하단 탭 시스템**: 거래 내역, 자산 곡선, 백테스트 리포트를 탭으로 분리하여 공간 효율성 극대화.
    *   **현대적 다크 테마**: 트레이딩 터미널 감성의 블루-다크 테마 적용.

3.  **검증 및 품질 보증 (Proof of Work)**:
    *   **신규 테스트 추가**: `tests/test_dashboard_live_sync.py`를 통해 실시간 지표 기록 및 조회 로직 검증 완료.
    *   **회귀 테스트 및 수정**: 기존 대시보드 테스트(`tests/test_dashboard.py`)를 최신 UI 스펙에 맞춰 업데이트하고, 발견된 UnboundLocalError 및 Jinja2 렌더링 오류 수정 완료.
    *   **최종 결과**: **68개 전체 테스트 케이스 100% Pass** 확인.

---

# Trading Session Log (2026-03-23) - Milestone: Data Sync & PnL Precision (v11.9.4)

## ✅ 완료된 작업
1.  **거래소 실시간 동기화 (Hyper-Precision PnL)**:
    -   단순히 차트 상의 종가가 아닌, 거래소 API가 리턴하는 실제 체결가(`average`)와 실지불 수수료(`fee`)를 사용하여 PnL을 계산하도록 `execute_entry`, `execute_exit` 로직 전면 개편.
    -   슬리피지로 인한 봇의 내부 계산과 실제 거래소 잔고 간의 오차 100% 제거.

2.  **독립적 자산 관리 (SEED-based Tracking)**:
    -   봇 전용 계정이 아닌 환경에서도 자산이 꼬이지 않도록, 전체 계좌 잔고를 가져오는 로직을 폐기.
    -   대신 봇 내부의 `SEED`에서 시작하여 실제 확정된 누적 PnL만 더해가는 방식으로 독립적인 자산 곡선(Equity Curve) 구축.

3.  **오버나이트 메가 최적화 도구 개발 (`mega_overnight_optimizer.py`)**:
    -   ETH, BTC, SOL, XRP, TRUMP, XAU 6개 종목에 대해 90일(분기) 단위로 데이터를 분할.
    -   CPU 코어를 100% 활용하는 병렬 처리(`ProcessPoolExecutor`)로 방대한 파라미터(Market/Sniper/Retest 모드 포함)를 밤새 고속으로 검증하고 CSV로 자동 저장하는 시스템 구축.

4.  **시스템 검증 및 무결성 확보**:
    -   거래소 API 모킹(Mocking)을 통한 실시간 동기화 로직 전용 테스트 `tests/test_live_sync_pnl.py` 추가.
    -   기존 63개 테스트에 신규 3개를 더해 **총 66개 전체 테스트 스위트 100% Pass** 달성.

---

# Trading Session Log (2026-03-23) - Milestone: Emergency Resilience (v11.9.1)

## ✅ 완료된 작업
1.  **긴급 청산 시스템 무결성 확보 (Force Exit)**:
    -   **거래소 실시간 동기화**: `/close_all` 명령 시 봇의 내부 상태에 의존하지 않고, 거래소 API를 통해 실제 포지션 수량을 직접 조회하여 청산하는 `force_exit()` 로직 도입.
    -   **비동기 병렬 처리**: `asyncio.gather`를 사용하여 모든 종목의 청산 및 취소 주문이 서버에 완전히 도달할 때까지 대기 후 프로세스 종료 보장.
    -   **ZeroDivision 방어**: PnL 계산 시 진입가가 0인 경우에 대비한 예외 처리 추가로 시스템 안정성 강화.

2.  **프로젝트 버전 업그레이드**:
    -   `src/config.py`, `README.md`, `CHANGELOG.md` 등 모든 관련 문서의 버전을 **v11.9.1**로 일괄 갱신.

---

# Trading Session Log (2026-03-23) - Milestone: Ambush Stabilization (v11.9.0)

## ✅ 완료된 작업
1.  **신호 안정성 강화 (Hysteresis)**:
    -   **필터 히스테리시스 (20%)**: 거래량(Volume)과 추세(ADX)가 기준치의 80% 수준까지 일시적으로 하락해도 대기 주문을 취소하지 않도록 보완.
    -   **근접도 히스테리시스 (2배)**: Sniper 모드에서 주문이 나간 후 가격이 멀어져도 **1.0%** 이내라면 주문을 유지하여 "주문 스팸" 원천 차단.
    -   **정각 신호 손실 방지 (Persistence)**: 새로운 1시간 캔들이 생성되는 시점에 거래량이 초기화되어 신호가 끊기는 문제를 해결하기 위해 **직전 봉 거래량 합산 검증** 도입.

2.  **검증 및 테스트 (QA)**:
    -   **전용 테스트 슈트**: `tests/test_hysteresis_persistence.py`를 통해 캔들 전환 및 히스테리시스 경계값 시뮬레이션 완료.
    -   **100% Pass**: 기존 59개 + 신규 4개 = **총 63개 테스트 케이스 통과**.
    -   **실전 파리티**: 백테스트 엔진(`run_streaming_backtest`)과 라이브 엔진의 로직을 완벽히 동기화.

3.  **코드 무결성 및 배포**:
    -   `strategy.py`, `live_bot_async.py` 리팩토링 및 깃헙 업로드 완료.
    -   **메가 최적화 도구군** 스테이징 및 커밋 완료.

---

# Trading Session Log (2026-03-22) - Milestone: Hyper-Realistic Simulation (v11.8.0)

## ✅ 완료된 작업
1.  **초정밀 스트리밍 시뮬레이터 (Hyper-Sim)**:
    -   **Look-ahead Bias 제거**: 매 분(1m)마다 1시간/4시간 지표를 재구성하는 `run_streaming_backtest` 도입.
    -   **하이퍼 최적화**: 넘파이(NumPy) 인덱스 기반 접근으로 1년치 정밀 시뮬레이션을 수분 내에 완료하는 성능 확보.
    -   **실시간 거래량 검증**: 봉 중간에 거래량 조건을 충족하는 시점을 정확히 시뮬레이션하여 진입가 현실화.

2.  **종합 시각 리포트 및 구조적 관리**:
    -   **4단 패널 시각화**: 가격/지표, ADX, 거래량, 자산 곡선을 한 장의 이미지로 생성 (`reports/` 내 PNG).
    -   **계층적 저장 구조**: `reports/{SYMBOL}/{MODE}/{TIMESTAMP}/` 경로를 통해 수천 개의 테스트 결과 체계적 관리.
    -   **대시보드 통합**: 웹 UI에서 백테스트 이미지 및 상세 거래 내역(CSV)을 즉시 확인 및 다운로드 기능 구현.

3.  **데이터 및 인프라 최적화**:
    -   **증분 업데이트**: `BinanceDataFetcher` 개선으로 기존 데이터 이후의 신규 데이터만 가져오는 초고속 싱크 지원.
    -   **DB 무결성**: 구버전(v11.2.0+)에서의 안전한 업데이트를 위한 자동 마이그레이션 및 상태 복구 로직 검증.

4.  **시스템 품질 및 검증 (QA)**:
    -   **테스트 케이스 현대화**: 리팩토링된 구조에 맞춰 59개의 전체 테스트 슈트 수정 및 보강.
    -   **100% Pass**: 모든 유닛/통합/E2E 테스트 성공 통과.

---



# Trading Session Log (2026-03-22) - Milestone: Relative Adaptive Trail (v11.6.0)

## ✅ 완료된 작업
1. **라이브 봇 전략 고도화 (v11.6.0)**:
   - `Retest Maker` (눌림목 매복) 로직 실전 이식 완료.
   - **개별 종목 정밀 제어**: 텔레그램 `/retest_on/off [SYMBOL]`, `/sniper_on/off [SYMBOL]` 명령어 구현.
   - **동적 모드 전환**: 실행 중인 봇의 재시작 없이 실시간으로 진입 전략 모드 변경 가능.

2. **시스템 무결성 검증**:
   - 52개 전체 테스트 케이스 통과 (100% Pass).
   - 신규 기능(Retest, Per-symbol toggle)에 대한 유닛 테스트 추가 및 검증 완료.
   - 기존 기능(Sniper, Sentinel, Async Loop)과의 호환성 보장.

3. **PnL 보고 체계 이원화**:
   - [Asset PnL | ROE] 병기 시스템 도입으로 거래소 앱과의 직관적 대조 가능.

---

## ✅ 완료된 작업
1. **진정한 메이커 진입 로직 구현 (v11.5.0)**:
   - `retest_maker` 모드 도입: 돌파 후 즉시 진입하지 않고, 돌파 레벨로의 '리테스트(눌림)'를 기다려 **지정가(Maker)**로 체결하는 전략.
   - 수수료 체계 현실화: 메이커(0.02%) vs 테이커(0.05%) 차등 적용 및 슬리피지 보정.

2. **3-Way 진입 전략 비교 분석**:
   - **Market**(봉 종가 진입), **Sniper**(돌파 레벨 정밀 테이커), **Retest_Maker**(눌림목 지정가) 세 가지 모드 동시 지원.
   - 최적화 엔진이 종목별 최적 모드를 자동 선별.

3. **데이터 기반 인사이트**:
   - **BTC/USDT**: `Retest_Maker`가 승리. 거래 횟수는 줄었으나 **MDD가 9% -> 5%로 급감**하며 효율성(7.37) 극대화.
   - **ETH/USDT**: 여전히 `Market` 진입이 가장 높은 효율(11.48)을 보임.
   - 종목의 변동성 성격에 따라 "추격"이냐 "매복"이냐를 선택해야 함을 입증.

---

## ✅ 완료된 작업
1. **차세대 실시간 비동기 엔진 완성 (v11.2.0)**:
   - 웹소켓 인트라-바 감지 로직으로 지연 시간 2초 이내 단축.
   - 불필요한 데이터 스트림 필터링 및 효율적 버퍼 관리.
   - **텔레그램 인터랙티브 버튼** 도입으로 사용자 편의성 극대화.

2. **시스템 아키텍처 현대화**:
   - YAML 기반 설정 시스템 도입 및 환경 변수 연동.
   - `CONFIG_GUIDE.md`, `WHITEPAPER.md` 등 전방위적 문서 업데이트.

3. **품질 보증 (QA)**:
   - 신규 기능 전용 테스트 포함 **47개 테스트 케이스 100% 통과**.
   - 코드와 문서의 버전 정보를 `11.2.0`으로 일괄 갱신.

---

# Trading Session Log (2026-03-21) - Resilience & Stability

## ✅ 완료된 작업
1. **버전 정보 중앙 집중화 및 동기화 (v11.1.1)**:
   - `src/config.py`의 `VERSION`을 `11.1.1`로 고정하고, 모든 로그/리포트가 이를 동적으로 참조하도록 개조.
   - `scripts/live_bot.py` 등 레거시 코드에 남아있던 **"V3" 하드코딩 문자열을 완전히 제거**하여 텔레그램 알림 일관성 확보.

2. **텔레그램 명령어 플러시(Flush) 도입**:
   - 봇 시작 시 서버에 쌓여있던 과거 명령어(예: `/close_all`)를 무시하도록 `offset` 기반 플러시 로직 구현.
   - 재시작 즉시 봇이 종료되는 현상 차단.

3. **NumPy 호환성 및 안정성 해결**:
   - NumPy 2.x 충돌 해결을 위해 `v1.26.4`로 강제 다운그레이드 및 `requirements.txt` 업데이트.

4. **검증 테스트 및 무결성 확보**:
   - `tests/test_resilience.py` 및 `tests/test_sentinel.py` 등 신규 로직 반영 및 픽스처 수정.
   - **최종 전체 테스트(38개) 100% 통과 (PASSED)** 확인.

5. **운영 회복력 강화**:
   - 바이낸스 API 타임아웃 대응을 위한 `fetch_ohlcv` 재시도 로직 및 메인 루프 예외 처리 강화.
   - `watchdog.py`를 통한 무중단 봇 운영 환경 완성.

---

# Trading Session Log (2026-03-14)

## ✅ 완료된 작업
1. **전략 진화**: 
   - 초기 `Supertrend + MACD + RSI` 전략에서 수익률 저조 확인.
   - 선행 지표 중심의 `Aggressive VBO (Donchian Channel Breakout)` 전략으로 전면 개조.
   - 거래량 2.0배 폭발 필터 추가로 가짜 돌파(Fakeout) 70% 차단 성공.

2. **백테스트 정밀화**:
   - 1시간봉 백테스트의 수익률 왜곡(Intra-bar bias) 발견.
   - **1분봉 체결 검증 로직** 도입하여 실전과 동일한 수익률(연 68.8%) 및 MDD(16.5%) 산출.

3. **파라미터 최적화**:
   - Grid Search를 통해 BTC, ETH, SOL, TRUMP 코인별 최적 세팅값 도출.
   - ETH(68.8%) 및 TRUMP(105.2%)에서 압도적 성과 확인.

4. **시스템 인프라 구축**:
   - `config.py` 중심의 모듈화 구조 완성.
   - SQLite 매매 이력 저장 및 `matplotlib` 리포트 자동 생성.
   - Telegram 실시간 알림 및 Flask 기반 웹 대시보드 개발.

## 📊 최종 성적표 (ETH/USDT, 1년 정밀 검증)
- **수익률**: +68.81%
- **MDD**: 16.52%
- **거래 횟수**: 119회
- **투자 효율(RAR)**: 4.17 (Return/MDD)

## 📝 다음 세션 제안 (To-do)
- [ ] **실전 복리 가동**: 단리가 아닌 수익금 재투자를 적용한 복리 매매 시뮬레이션 고도화.
- [ ] **포트폴리오 통합**: ETH와 TRUMP를 동시에 매매할 때의 통합 자산 곡선 검증.
- [ ] **에러 핸들링 강화**: 바이낸스 API 응답 지연이나 서버 끊김에 대비한 자동 재시작 로직 추가.
- [ ] **텔레그램 명령**: 텔레그램 채팅으로 현재 잔고나 리포트 이미지를 즉시 요청하는 기능.

---
## ✅ 2026-03-20: V3 전략 진화 (ADX + Adaptive Trail) 완료

1. **전략 고도화 (V3)**:
   - **ADX 필터 도입**: 횡보장 가짜 돌파 억제를 위해 ADX 15~25 필터 적용. (MDD 대폭 감소)
   - **적응형 트레일링 (Adaptive Trail)**: 수익률 10%, 20% 돌파 시 ATR 배수를 타이트하게 좁혀 수익 보존력 극대화.
   - **분할 익절 실험**: 분할 익절보다 가변 트레일링이 수익률 보존에 더 효율적임을 검증하여 최종 채택.

2. **V3 최적화 결과**:
   - **TRUMP/USDT**: 수익률 **+210.07%** | MDD 17.29% (최적 파라미터 도출)
   - **XAU/USDT**: 수익률 **+186.89%** | MDD **12.55%** (금 선물 시장 압도적 효율성 확인)
   - **ETH/USDT**: 수익률 **+161.44%** | MDD 19.80% (안정적 우상향 복구)

3. **시스템 강화**:
   - `live_bot.py`에 가변 트레일링 로직 및 서버사이드 손절 동기화 완벽 통합.
   - `tests/test_strategy_v2.py`에 V3 로직(ADX, Adaptive Trail) 유닛 테스트 추가 및 통과.

## 📊 V3 최종 성적 (최고 성적 종목 기준)
- **대상**: TRUMP/USDT, XAU/USDT (Gold)
- **최고 수익률**: +210.07% (1년 복리 시뮬레이션 급 성과)
- **최저 MDD**: 12.55%
- **거래 효율**: 12.15 (Return/MDD) - S-Tier 달성

## 📝 다음 세션 제안 (To-do)
- [ ] **멀티 심볼 동시 가동**: 자산 배분(Asset Allocation) 엔진 추가로 ETH, TRUMP, XAU 동시 매매 최적화.
- [ ] **대시보드 업그레이드**: Flask 대시보드에서 V3 지표(ADX, Trail Level) 실시간 시각화 지원.
- [ ] **슬리피지 분석**: 실전 Dry Run 데이터 분석을 통해 실제 슬리피지 보정값 정밀화.

---
**Status**: V3 Strategy Verified & Ready for Production.
\n### [2026-03-20] Multi-Symbol Portfolio Manager Implementation\n- **Feature**: Centralized PortfolioManager for multi-symbol capital allocation.\n- **Risk Engine**: Dual-constraint sizing (Risk-based & Margin-based).\n- **Orchestrator**: New `live_bot_multi.py` to monitor multiple pairs concurrently.\n- **Database**: Updated DBManager to support symbol-specific trade tracking.\n- **Validation**: 23/23 tests passed, including new portfolio logic tests.
\n### [2026-03-20] Portfolio Dashboard V4 Upgrade\n- **UI/UX**: Modernized dashboard with real-time portfolio monitoring.\n- **Active Stats**: Real-time PnL tracking for all active positions.\n- **KPIs**: Added Portfolio-wide balance, Win Rate, and Symbol Weight distribution.\n- **UX**: 30-second auto-refresh for live market observation.
\n### [2026-03-21] v7.0.1: WebSocket Async Engine & Atomic Safety\n- **Innovation**: Fully migrated to Asynchronous WebSocket architecture for near-zero latency.\n- **Safety**: Implemented 'Atomic Order' logic - immediate liquidation if SL fails to place.\n- **Resilience**: Added granular error handling with exponential backoff for network errors.\n- **Documentation**: Updated README and Whitepaper to v7 specs.\n- **Verification**: 27/27 unit & integration tests passed.
\n### [2026-03-21] v8.0.0: Command & Control System\n- **Operations**: Integrated bidirectional Telegram commands (/status, /stop, /close_all).\n- **Monitoring**: Implemented Hourly Heartbeat reports for remote health checks.\n- **Security**: Authorized command execution with chat_id filtering.\n- **Refinement**: Fully independent capital isolation and state recovery (v6/v7 features) preserved.\n- **Verification**: 27/27 unit & integration tests passed.
\n### [2026-03-21] v9.0.0: Self-Adaptive Optimizer Engine\n- **Intelligence**: Implemented Walk-Forward optimization based on recent 30-day data.\n- **Control**: Integrated /optimize [SYMBOL] command for live parameter tuning.\n- **Mechanism**: Added Hot-Reload capability to update settings without bot restart.\n- **Refinement**: Switched to Efficiency-based (Return/MDD) parameter selection.\n- **Robustness**: Fixed circular imports and duplicate class definitions.\n- **Verification**: 29/29 unit & integration tests passed.
\n### [2026-03-21] v10.0.0: The Sentinel & Command Validator\n- **Intelligence**: Implemented hybrid optimization proposal system (The Sentinel).\n- **Interface**: Detailed Telegram Command Guide added to documentation.\n- **Validator**: New `scripts/test_telegram_commands.py` for real-time connection checks.\n- **Security**: Hardened chat_id authorization for all remote commands.\n- **Testing**: Added 4 new tests for Sentinel logic; total 31/31 tests passed.
\n### [2026-03-21] v11.0.0: The Precision Sniper\n- **Entry Engine**: Implemented Pre-emptive Limit Entry (Sniper) to capture Maker fees and eliminate slippage.\n- **Precision Filter**: Enforced strict 4-Pillar validation (Price, Vol, ADX, EMA) to avoid fakeouts.\n- **Control**: Added /sniper_on and /sniper_off remote kill switches.\n- **Safety**: Fully integrated with Atomic SL on fill events.\n- **Verification**: 34/34 tests passed, including new Sniper logic validation.
\n### [2026-03-21] v11.0.0: The Sniper Strategy Validation\n- **Simulation**: Developed `backtest/sniper_backtester.py` to verify economic impact.\n- **S-Tier Performance**: Confirmed Sniper mode achieves up to +835% return by eliminating 0.5% slippage.\n- **Alpha**: Proven +751% alpha gain on TRUMP/USDT compared to market-taker entry.\n- **Documentation**: README and Whitepaper updated with intra-bar stress test results.\n- **Status**: V11 production-ready with proven mathematical edge.
\n### [2026-04-06] v13.1.10: Event-Driven Exit & Full Stability\n- **Stability**: Fixed a critical `ZeroDivisionError` occurring after Sniper fills by implementing `last_price` backups and `entry_price` guards across the codebase.\n- **Refactor**: Redesigned the exit mechanism to be "Exchange-First," trusting the exchange's SL trigger and `on_order_update` events rather than redundant market orders. This eliminated race conditions during SL hits.\n- **Resilience**: Enhanced `on_order_update` to handle exit fills based on order direction (side) rather than just static order IDs, allowing recovery from manual SL modifications.\n- **Verification**: Verified the entire system with a full 75-test suite, all passing. Integrated a new `test_sl_robustness.py` and updated E2E simulations.\n- **Version**: Bumped to **13.1.10** and updated all documentation, dashboard references, and example configurations.\n- **Resilience**: Implemented 'Last Will' Telegram notification for crashes and termination signals.\n- **Stability**: Developed `scripts/watchdog.py` for external process monitoring and auto-restart.\n- **Refinement**: Fixed capital tracking display in /status and synced version to v11.0.1.\n- **Maintenance**: Verified resource cleanup (exchange.close) and 34/34 tests passing.
