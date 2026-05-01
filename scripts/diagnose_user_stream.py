import argparse
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from urllib.parse import quote

import ccxt.async_support as ccxt
import websockets

from src.config import CONFIG


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
)
logger = logging.getLogger("UserStreamDiag")


def mask(value):
    if not value:
        return "None"
    return f"{value[:6]}***{value[-4:]}"


async def get_fapi_listen_key(exchange):
    response = await exchange.fapiPrivatePostListenKey()
    return response.get("listenKey")


async def print_account_summary(exchange):
    account = await exchange.fapiPrivateV2GetAccount()
    logger.info(
        "FAPI account reachable: canTrade=%s, multiAssetsMargin=%s, feeTier=%s",
        account.get("canTrade"),
        account.get("multiAssetsMargin"),
        account.get("feeTier"),
    )


async def print_recent_orders(exchange, symbols):
    logger.info("Checking recent USD-M Futures orders visible to this API key...")
    seen_any = False

    for symbol in symbols:
        try:
            orders = await exchange.fetch_orders(symbol, limit=5)
        except Exception as exc:
            logger.warning("Could not fetch recent orders for %s: %s", symbol, exc)
            continue

        if not orders:
            logger.info("%s: no recent orders visible", symbol)
            continue

        seen_any = True
        logger.info("%s: %s recent orders visible", symbol, len(orders))
        for order in orders[-5:]:
            ts = order.get("timestamp")
            dt = (
                datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
                if ts else "unknown-time"
            )
            logger.info(
                "  %s id=%s side=%s type=%s status=%s price=%s amount=%s filled=%s",
                dt,
                order.get("id"),
                order.get("side"),
                order.get("type"),
                order.get("status"),
                order.get("price"),
                order.get("amount"),
                order.get("filled"),
            )

    if not seen_any:
        logger.warning(
            "No recent orders were visible for the checked symbols. If you just placed a test order, "
            "verify the symbol, account, and market type match this bot's API key."
        )


async def watch_url(url, label, duration):
    logger.info("Connecting %s: %s", label, url)
    deadline = time.time() + duration
    count = 0

    try:
        async with websockets.connect(url, ping_interval=20, ping_timeout=15) as ws:
            logger.info("Connected %s. Now waiting for private account events...", label)
            while time.time() < deadline:
                timeout = max(0.1, min(5, deadline - time.time()))
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=timeout)
                except asyncio.TimeoutError:
                    continue

                count += 1
                payload = json.loads(message)
                data = payload.get("data", payload) if isinstance(payload, dict) else payload
                logger.info("[%s] EVENT #%s: %s", label, count, json.dumps(data, ensure_ascii=False)[:1200])
    except Exception as exc:
        logger.error("%s failed: %s", label, exc)

    logger.info("%s finished. private_event_count=%s", label, count)
    return count


async def place_and_cancel_probe_order(
    exchange,
    symbol,
    side,
    amount,
    price_factor,
    wait_before_cancel,
    start_delay,
):
    if start_delay > 0:
        logger.info("Waiting %.1fs before creating probe order so streams can subscribe...", start_delay)
        await asyncio.sleep(start_delay)

    ticker = await exchange.fetch_ticker(symbol)
    last_price = float(ticker["last"])
    if side == "buy":
        raw_price = last_price * price_factor
    else:
        raw_price = last_price * (2 - price_factor)

    price = float(exchange.price_to_precision(symbol, raw_price))
    amount = float(exchange.amount_to_precision(symbol, amount))

    min_cost = exchange.market(symbol).get("limits", {}).get("cost", {}).get("min") or 20
    notional = amount * price
    if notional < min_cost:
        adjusted_amount = (min_cost / price) * 1.05
        amount = float(exchange.amount_to_precision(symbol, adjusted_amount))
        notional = amount * price
        logger.info(
            "Adjusted probe amount to satisfy min notional: amount=%s notional=%.4f min_cost=%s",
            amount,
            notional,
            min_cost,
        )

    if amount <= 0:
        raise ValueError(f"Probe amount became zero after precision formatting: {amount}")

    logger.info(
        "Creating probe %s LIMIT %s %s at %s. Last price=%s, price_factor=%s",
        side.upper(),
        amount,
        symbol,
        price,
        last_price,
        price_factor,
    )
    logger.warning("This is a REAL USD-M Futures order. It is postOnly and far from market, but still uses your account.")

    order = await exchange.create_order(
        symbol,
        "limit",
        side,
        amount,
        price,
        params={"postOnly": True},
    )
    order_id = order["id"]
    logger.info("Probe order created: id=%s status=%s", order_id, order.get("status"))

    await asyncio.sleep(wait_before_cancel)

    try:
        cancelled = await exchange.cancel_order(order_id, symbol)
        logger.info("Probe order cancelled: id=%s status=%s", order_id, cancelled.get("status"))
    except Exception as exc:
        logger.error("Failed to cancel probe order %s: %s", order_id, exc)
        raise


async def main():
    parser = argparse.ArgumentParser(
        description="Diagnose Binance USD-M Futures user-data stream events."
    )
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument(
        "--symbol",
        action="append",
        dest="symbols",
        help="Symbol to check for recent USD-M Futures orders. Can be passed multiple times.",
    )
    parser.add_argument(
        "--probe-order",
        action="store_true",
        help="Create and cancel one far-from-market postOnly USD-M Futures limit order to trigger user-stream events.",
    )
    parser.add_argument("--probe-symbol", default=None)
    parser.add_argument("--probe-side", choices=["buy", "sell"], default="buy")
    parser.add_argument("--probe-amount", type=float, default=None)
    parser.add_argument(
        "--probe-price-factor",
        type=float,
        default=0.5,
        help="For buy: price=last*factor. For sell: price=last*(2-factor). Default places order ~50%% away.",
    )
    parser.add_argument("--probe-wait-before-cancel", type=float, default=3.0)
    parser.add_argument("--probe-start-delay", type=float, default=2.0)
    args = parser.parse_args()

    exchange = ccxt.binance({
        "apiKey": CONFIG["BINANCE_API_KEY"],
        "secret": CONFIG["BINANCE_SECRET"],
        "options": {"defaultType": "future"},
    })

    try:
        await print_account_summary(exchange)
        await exchange.load_markets()
        symbols = args.symbols or CONFIG.get("SYMBOLS_LIST", [])
        await print_recent_orders(exchange, symbols)

        listen_key = await get_fapi_listen_key(exchange)
        logger.info("FAPI listenKey: %s", mask(listen_key))
        encoded_listen_key = quote(listen_key, safe="")
        order_event = quote("ORDER_TRADE_UPDATE", safe="")

        urls = [
            (
                f"wss://fstream.binance.com/private/ws?listenKey={encoded_listen_key}&events={order_event}",
                "new-private/ws-order",
            ),
            (
                f"wss://fstream.binance.com/private/stream?listenKey={encoded_listen_key}&events={order_event}",
                "new-private/stream-order",
            ),
            (f"wss://fstream.binance.com/ws/{listen_key}", "fstream/ws"),
            (f"wss://fstream.binance.com/stream?streams={listen_key}", "fstream/stream"),
            (f"wss://fstream.binancefuture.com/ws/{listen_key}", "binancefuture/ws"),
            (f"wss://fstream.binancefuture.com/stream?streams={listen_key}", "binancefuture/stream"),
        ]

        logger.info(
            "Place or cancel a SMALL USD-M Futures order now, using the same Binance account/API key. "
            "Listening for %ss...",
            args.seconds,
        )

        tasks = [watch_url(url, label, args.seconds) for url, label in urls]
        if args.probe_order:
            probe_symbol = args.probe_symbol or (symbols[0] if symbols else None)
            if not probe_symbol:
                raise ValueError("--probe-symbol is required when no config SYMBOLS_LIST exists")

            market = exchange.market(probe_symbol)
            min_amount = market.get("limits", {}).get("amount", {}).get("min")
            probe_amount = args.probe_amount or min_amount
            if not probe_amount:
                raise ValueError(
                    "--probe-amount is required because the exchange metadata did not provide a minimum amount"
                )

            tasks.append(
                place_and_cancel_probe_order(
                    exchange,
                    probe_symbol,
                    args.probe_side,
                    probe_amount,
                    args.probe_price_factor,
                    args.probe_wait_before_cancel,
                    args.probe_start_delay,
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        counts = results[:len(urls)]
        for result in results[len(urls):]:
            if isinstance(result, Exception):
                logger.error("Probe order task failed: %s", result)
        logger.info("Summary: %s", dict(zip([label for _, label in urls], counts)))
    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(main())
