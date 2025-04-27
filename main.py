# Flask 디버깅용 서버 코드 - 파일 저장 버전

from flask import Flask, request, jsonify
from datetime import datetime
import pandas as pd
import os
import json
import threading
import time
import requests

app = Flask(__name__)

# === 설정 ===
LOG_PATH = "./trade_log.csv"
POSITION_PATH = "./positions.json"
SAVE_LOG_PATH = "./log.txt"  # 🔥 추가: 수신 기록 저장용
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
                return data if isinstance(data, list) else []
            except:
                return []
    return []

def save_positions(positions):
    with open(POSITION_PATH, 'w') as f:
        json.dump(positions, f, indent=2)

positions = load_positions()

# === Webhook 수신 ===
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        # ✨ request가 json이 아닐 경우도 대비
        if request.is_json:
            data = request.get_json()
        else:
            data = json.loads(request.data.decode("utf-8"))

        # 🔥 파일로 수신 데이터 저장
        with open(SAVE_LOG_PATH, "a") as f:
            f.write(f"\n[{datetime.now()}] 수신 데이터: {json.dumps(data)}\n")

        if not data:
            return jsonify({"status": "no data"}), 400

        action = data.get("action")
        price = data.get("price")

        if action not in ["long", "short"]:
            with open(SAVE_LOG_PATH, "a") as f:
                f.write(f"[{datetime.now()}] 경고: 잘못된 action 수신\n")
            return jsonify({"status": "invalid action"}), 400
        if price is None:
            with open(SAVE_LOG_PATH, "a") as f:
                f.write(f"[{datetime.now()}] 경고: price 누락\n")
            return jsonify({"status": "invalid price"}), 400

        price = float(price)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        open_positions = [p for p in positions if p.get("status") == "open"]

        if len(open_positions) >= MAX_POSITIONS:
            with open(SAVE_LOG_PATH, "a") as f:
                f.write(f"[{now}] 최대 포지션 초과로 진입 무시\n")
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

        with open(SAVE_LOG_PATH, "a") as f:
            f.write(f"[{now}] {action.upper()} 진입 기록 저장 완료 (진입가: {price}, 금액: {amount} USDT)\n")

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        with open(SAVE_LOG_PATH, "a") as f:
            f.write(f"[{datetime.now()}] 오류 발생: {str(e)}\n")
        return jsonify({"status": "error", "message": str(e)}), 500

# === 현재 Bar Index 계산 ===
def get_current_bar_index():
    return int(datetime.now().timestamp() // 300)

# === 서버 실행 ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
