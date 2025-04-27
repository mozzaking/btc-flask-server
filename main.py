# 수정된 Flask 서버 코드 - positions.json 없으면 자동 생성 포함

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
BACKUP_DIR = "./backup_logs"
os.makedirs(BACKUP_DIR, exist_ok=True)

BINANCE_API_URL = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=1"
holdBars = 5
forceExitBars = 50
FEE_RATE_PER_SIDE = 0.0005
MAX_POSITIONS = 5
INITIAL_BALANCE = 1000
POSITION_RATIO = 0.19

# === positions.json 초기화 ===
if not os.path.exists(POSITION_PATH):
    with open(POSITION_PATH, 'w') as f:
        json.dump([], f)
    print("[초기화] positions.json 파일 생성 완료")

# === 포지션 불러오기 및 저장 ===
def load_positions():
    with open(POSITION_PATH, 'r') as f:
        try:
            data = json.load(f)
            return data if isinstance(data, list) else []
        except:
            return []

def save_positions(positions):
    with open(POSITION_PATH, 'w') as f:
        json.dump(positions, f, indent=2)

positions = load_positions()

# === Webhook 수신 ===
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = json.loads(request.data.decode("utf-8"))

        print(f"[수신 데이터] {data}")

        if not data:
            print("[경고] 수신 데이터 없음")
            return jsonify({"status": "no data"}), 400

        action = data.get("action")
        price = data.get("price")

        print(f"[수신 Action] {action}")
        print(f"[수신 Price] {price}")

        if action not in ["long", "short"] or price is None:
            print("[경고] action 또는 price 이상함")
            return jsonify({"status": "invalid data"}), 400

        price = float(price)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        open_positions = [p for p in positions if p.get("status") == "open"]

        if len(open_positions) >= MAX_POSITIONS:
            print(f"[{now}] 최대 포지션 초과로 진입 무시")
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
        print(f"[{now}] {action.upper()} 진입 기록 저장 완료 (진입가: {price}, 금액: {amount} USDT)")

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print(f"[오류] webhook 처리 실패: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# === 현재 Bar Index 계산 ===
def get_current_bar_index():
    return int(datetime.now().timestamp() // 300)

# === 서버 실행 ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
