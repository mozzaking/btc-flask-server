# Flask 서버 코드 - Render 배포용 버전 (ngrok 제거)

from flask import Flask, request, jsonify
from datetime import datetime
import pandas as pd
import os
import json
import threading
import time
import requests
import atexit
import signal

app = Flask(__name__)

# === 설정 ===
LOG_PATH = "./trade_log.csv"
POSITION_PATH = "./positions.json"
BACKUP_DIR = "./backup_logs"
os.makedirs(BACKUP_DIR, exist_ok=True)

BINANCE_API_URL = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=1"
holdBars = 5
forceExitBars = 50

FEE_RATE_PER_SIDE = 0.0005
MAX_POSITIONS = 5
INITIAL_BALANCE = 1000
POSITION_RATIO = 0.19

# === 포지션 불러오기 및 저장 ===
def load_positions():
    if os.path.exists(POSITION_PATH):
        with open(POSITION_PATH, 'r') as f:
            try:
                data = json.load(f)
                if not isinstance(data, list):
                    raise Exception("positions.json이 리스트 형식이 아님")
                for item in data:
                    if not isinstance(item, dict):
                        raise Exception(f"positions 내부에 이상한 데이터 발견: {item}")
                return data
            except Exception as e:
                print(f"[경고] positions.json 파일 문제: {e}, 초기화합니다.")
                return []
    return []

def save_positions(positions):
    with open(POSITION_PATH, 'w') as f:
        json.dump(positions, f, indent=2)

positions = load_positions()

# === Webhook 수신 ===
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    action = data.get("action")
    price = float(data.get("price"))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    open_positions = [p for p in positions if p.get("status") == "open"]

    if action in ["short", "long"]:
        if len(open_positions) >= MAX_POSITIONS:
            print(f"[{now}] 최대 포지션 초과로 진입 무시: {action.upper()} at {price}")
            return jsonify({"status": "max positions reached"}), 200

        amount = INITIAL_BALANCE * POSITION_RATIO

        positions.append({
            "entry_time": now,
            "entry_price": price,
            "amount": amount,
            "direction": action,
            "entry_bar_index": get_current_bar_index(),
            "max_profit_ratio": 0,
            "status": "open"
        })
        save_positions(positions)
        print(f"[{now}] {action.upper()} 진입 수신: {price} (진입금액: {amount} USDT)")

    return jsonify({"status": "ok"}), 200

# === 현재 Bar Index 계산 ===
def get_current_bar_index():
    return int(datetime.now().timestamp() // 300)

# === 실시간 가격 감시 ===
def get_close_price():
    response = requests.get(BINANCE_API_URL, timeout=10)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise Exception(f"Unexpected close price response: {data}")
    return float(data[0][4])

def monitor_market():
    while True:
        try:
            close_price = get_close_price()
        except Exception as e:
            print(f"[오류] close_price 가져오기 실패: {e}")
            time.sleep(10)
            continue

        try:
            ma200 = calculate_ma200()
        except Exception as e:
            print(f"[오류] MA200 계산 실패: {e}")
            time.sleep(10)
            continue

        current_bar = get_current_bar_index()

        try:
            for pos in positions:
                if isinstance(pos, dict) and pos.get("status") == "open":
                    direction = pos["direction"]
                    entry_bar = pos["entry_bar_index"]
                    entry_price = pos["entry_price"]
                    amount = pos["amount"]
                    hold = current_bar - entry_bar >= holdBars
                    force_exit = current_bar - entry_bar >= forceExitBars
                    ma_exit = (close_price > ma200) if direction == "short" else (close_price < ma200)

                    profit_ratio = (entry_price - close_price) / entry_price if direction == "short" else (close_price - entry_price) / entry_price
                    pos["max_profit_ratio"] = max(pos.get("max_profit_ratio", 0), profit_ratio)

                    if pos["max_profit_ratio"] > 0.05:
                        trail_perc = 0.05
                    elif pos["max_profit_ratio"] > 0.04:
                        trail_perc = 0.04
                    elif pos["max_profit_ratio"] > 0.03:
                        trail_perc = 0.03
                    elif pos["max_profit_ratio"] > 0.02:
                        trail_perc = 0.02
                    elif pos["max_profit_ratio"] > 0.01:
                        trail_perc = 0.01
                    else:
                        trail_perc = 0.005

                    trail_trigger = profit_ratio <= (pos["max_profit_ratio"] - trail_perc / 2)

                    if (hold and ma_exit) or force_exit or (hold and trail_trigger):
                        pos["status"] = "closed"
                        exit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        gross = (entry_price - close_price) if direction == "short" else (close_price - entry_price)
                        gross_usdt = gross / entry_price * amount
                        fee = amount * FEE_RATE_PER_SIDE * 2
                        net = gross_usdt - fee
                        net_pct = net / amount
                        result = "profit" if net > 0 else "loss"

                        trade = {
                            "entry_time": pos["entry_time"],
                            "exit_time": exit_time,
                            "direction": pos["direction"],
                            "entry_price": entry_price,
                            "exit_price": close_price,
                            "amount": amount,
                            "gross_pnl": round(gross_usdt, 2),
                            "fee": round(fee, 5),
                            "net_pnl": round(net, 2),
                            "net_pct": round(net_pct, 5),
                            "result": result
                        }

                        print(f"[{exit_time}] {direction.upper()} 포지션 청산: {close_price}, 수익: {round(net, 2)} USDT")

                        df = pd.DataFrame([trade])
                        if not os.path.exists(LOG_PATH):
                            df.to_csv(LOG_PATH, mode='w', index=False)
                        else:
                            df.to_csv(LOG_PATH, mode='a', header=False, index=False)

            save_positions(positions)
        except Exception as e:
            print(f"[오류] 포지션 업데이트 실패: {e}")

        time.sleep(300)

# === MA200 계산 ===
def calculate_ma200():
    try:
        url = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=200"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise Exception(f"Unexpected MA200 response: {data}")
        closes = [float(candle[4]) for candle in data]
        return sum(closes) / len(closes)
    except Exception as e:
        print(f"[오류] MA200 계산 실패: {e}")
        return 0

# === 종료 시 백업 ===
def backup_on_exit():
    if os.path.exists(LOG_PATH):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"backup_{timestamp}.csv")
        pd.read_csv(LOG_PATH).to_csv(backup_path, index=False)
        print(f"[백업] trade_log.csv → {backup_path}")

atexit.register(backup_on_exit)

# === 서버 실행 ===
if __name__ == "__main__":
    threading.Thread(target=monitor_market, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
