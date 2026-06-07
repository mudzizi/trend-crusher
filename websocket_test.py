import websocket
import time
import json

def on_message(ws, message):
    data = json.loads(message)
    print(data)

def on_close(ws, *args):
    print("closed")

def connect():
    ws = websocket.WebSocketApp(
        "wss://stream.binance.com:9443/ws/btcusdt@trade",
        on_message=on_message,
        on_close=on_close
    )
    ws.run_forever(ping_interval=20, ping_timeout=10)

if __name__ == "__main__":
    while True:
        try:
            connect()
        except Exception as e:
            print("reconnect...", e)
            time.sleep(3)
