from flask import Flask, request
import json

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    print("[RAW 수신 시작]")
    print(request.data)  # 🔥 Raw 데이터 출력
    try:
        payload = request.get_json(force=True)  # 🔥 강제 json 변환
        print(f"[Parsed JSON] {payload}")
    except Exception as e:
        print(f"[파싱 실패] {e}")

    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
