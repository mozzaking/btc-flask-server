from flask import Flask, request
import csv
import json
from datetime import datetime

app = Flask(__name__)

# 초기 설정
initial_balance = 1000.0  # 시작 시드
balance = initial_balance
position = None
fee_rate = 0.0008  # 0.08%
invest_ratio = 0.9  # 90% 진입

# 파일 초기화
csv_file = 'mock_trades.csv'
with open(csv_file, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["Entry Time", "Exit Time", "Entry Price", "Exit Price", "Position Size", "Profit %", "Balance"])

@app.route('/webhook', methods=['POST'])

def webhook():
    global balance,position
    
    print("[DEBUG] Webhook endpoint triggered", flush=True)


    # === JSON 파싱 처리 보완 ===
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = json.loads(request.data.decode('utf-8'))
    except Exception as e:
        print(f"[오류] JSON 파싱 실패: {e}", flush=True)
        return 'Invalid JSON', 415

    print(f"[수신 데이터] {data}", flush=True)

    signal = data.get('signal')
    price = float(data.get('price'))
    time = data.get('time')

    if signal == 'LONG_SIGNAL':
        if position is None:
            position_size = balance * invest_ratio
            entry_price = price * (1 + fee_rate)  # 매수 시 수수료 반영

            position = {
                'entry_time': time,
                'entry_price': entry_price,
                'size': position_size
            }

            print(f"[진입] {time} | 가격: {price:.2f} | 포지션 크기: {position_size:.2f} USDT (수수료 포함)", flush=True)

    elif signal in ['EXIT_SIGNAL', 'TRAIL_EXIT_SIGNAL']:
        if position is not None:
            exit_price = price * (1 - fee_rate)  # 매도 시 수수료 반영
            entry_price = position['entry_price']
            size = position['size']

            profit_ratio = (exit_price - entry_price) / entry_price
            profit_amount = size * profit_ratio
            balance += profit_amount

            print(f"[청산] {time} | 가격: {price:.2f} | 수익률: {profit_ratio*100:.2f}% | 수익: {profit_amount:.2f} USDT | 잔고: {balance:.2f} USDT", flush=True)

            save_trade(position['entry_time'], time, entry_price, exit_price, size, profit_ratio, balance)

            position = None

    return 'ok', 200


def save_trade(entry_time, exit_time, entry_price, exit_price, size, profit_ratio, balance):
    with open(csv_file, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([entry_time, exit_time, f"{entry_price:.2f}", f"{exit_price:.2f}", f"{size:.2f}", f"{profit_ratio*100:.2f}", f"{balance:.2f}"])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
