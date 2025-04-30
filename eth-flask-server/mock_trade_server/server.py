from flask import Flask, request
import csv
from datetime import datetime
import pytz
import json

app = Flask(__name__)

csv_file = "eth_mock_trades.csv"
initial_balance = 1000.0
balance = initial_balance
position = None
fee_rate = 0.0005  # 진입 + 청산 각 0.05%
invest_ratio = 0.9

# CSV 파일 헤더 작성
with open(csv_file, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["Entry Time", "Exit Time", "Direction", "Entry Price", "Exit Price",
                     "Position Size", "Profit USDT", "Fee USDT", "Net Profit USDT", "Balance"])

def parse_kst_timestamp(iso_time):
    try:
        utc_dt = datetime.strptime(iso_time, "%Y-%m-%dT%H:%M:%SZ")
        kst_dt = utc_dt.replace(tzinfo=pytz.utc).astimezone(pytz.timezone('Asia/Seoul'))
        return kst_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"[오류] 시간 파싱 실패: {e}")
        return iso_time

@app.route('/webhook', methods=['POST'])
def webhook():
    global balance, position

    print(f"[DEBUG] Webhook endpoint triggered")

    try:
        data = request.get_json(force=True)
        print(f"[수신 데이터] {data}")
    except Exception as e:
        print(f"[오류] JSON 파싱 실패: {e}")
        return 'Invalid JSON', 415

    signal = data.get("signal")
    price_raw = data.get("price")
    time_raw = data.get("time")

    if not signal or not price_raw or not time_raw:
        print(f"[오류] 필드 누락 - signal: {signal}, price: {price_raw}, time: {time_raw}")
        return 'Missing required fields', 400

    try:
        price = float(price_raw)
    except Exception as e:
        print(f"[오류] price 변환 실패: {e}")
        return 'Invalid price format', 400

    kst_time = parse_kst_timestamp(time_raw)
    print(f"[수신] {kst_time} | {signal} | 가격: {price:.2f}")

    if signal in ['LONG_SIGNAL', 'SHORT_SIGNAL']:
        direction = "long" if signal == "LONG_SIGNAL" else "short"

        if position is not None:
            exit_price = price * (1 - fee_rate if position['direction'] == 'long' else 1 + fee_rate)
            entry_price = position['entry_price']
            size = position['size']
            profit_ratio = (exit_price - entry_price) / entry_price if position['direction'] == "long" else (entry_price - exit_price) / entry_price
            gross_profit = size * profit_ratio
            fee_usdt = size * fee_rate * 2
            net_profit = gross_profit - fee_usdt
            balance += net_profit

            print(f"[청산] {kst_time} | 방향: {position['direction'].upper()} | 수익: {net_profit:.2f} USDT | 잔고: {balance:.2f} USDT")

            save_trade(position['entry_time'], kst_time, position['direction'].upper(),
                       entry_price, exit_price, size, gross_profit, fee_usdt, net_profit, balance)

        entry_price = price * (1 + fee_rate if direction == 'long' else 1 - fee_rate)
        size = balance * invest_ratio
        position = {
            'entry_time': kst_time,
            'entry_price': entry_price,
            'size': size,
            'direction': direction
        }

        print(f"[진입] {kst_time} | 방향: {direction.upper()} | 가격: {price:.2f} | 포지션 크기: {size:.2f} USDT")

    elif signal in ['EXIT_SIGNAL', 'TRAIL_EXIT_SIGNAL']:
        if position is not None:
            exit_price = price * (1 - fee_rate if position['direction'] == 'long' else 1 + fee_rate)
            entry_price = position['entry_price']
            size = position['size']
            profit_ratio = (exit_price - entry_price) / entry_price if position['direction'] == "long" else (entry_price - exit_price) / entry_price
            gross_profit = size * profit_ratio
            fee_usdt = size * fee_rate * 2
            net_profit = gross_profit - fee_usdt
            balance += net_profit

            print(f"[청산] {kst_time} | 방향: {position['direction'].upper()} | 수익: {net_profit:.2f} USDT | 잔고: {balance:.2f} USDT")

            save_trade(position['entry_time'], kst_time, position['direction'].upper(),
                       entry_price, exit_price, size, gross_profit, fee_usdt, net_profit, balance)

            position = None

    return 'ok', 200

def save_trade(entry_time, exit_time, direction, entry_price, exit_price, size, profit, fee, net, balance):
    with open(csv_file, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([entry_time, exit_time, direction, f"{entry_price:.2f}", f"{exit_price:.2f}", f"{size:.2f}",
                         f"{profit:.2f}", f"{fee:.2f}", f"{net:.2f}", f"{balance:.2f}"])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
