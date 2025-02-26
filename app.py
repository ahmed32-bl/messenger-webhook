import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

VERIFY_TOKEN = "workshop_chatbot_123"  # تأكد من أنه نفس التوكن في فيسبوك
PAGE_ACCESS_TOKEN = "EAANEgEzn4hwBOwxeBNDM0YR3SB952FCzpSsOurktbYtAbAI6beIwrK8WhZCtgYDP1HNJmOGD97zqV6NAlxucnZABI7C58PqNERdZArL6O4P0NYHYhuwZAPQX8vvCyhQKQTUTyeBYI4tymgkxwz6Xw9HDeibYBMUSdeR4rREcr9fBT3ZAbrujogdIvFBBJXnKJJbryoREMrHeOZAGJ8zQZDZD"  # ضع التوكن الخاص بصفحة ماسنجر هنا
import os
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    """إرسال الرسالة إلى ChatGPT والحصول على الرد"""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-3.5-turbo",  # أو استخدم "gpt-3.5-turbo" إذا كنت تريد خيارًا أرخص
        "messages": [{"role": "user", "content": message}]
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()["choices"][0]["message"]["content"]

@app.route("/", methods=["GET"])
def home():
    return "Messenger Webhook is running!"

@app.route("/webhook", methods=["GET"])
def verify():
    """التحقق من Webhook لفيسبوك"""
    token_sent = request.args.get("hub.verify_token")
    if token_sent == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Invalid verification token", 403

@app.route("/webhook", methods=["POST"])
def receive_message():
    """استقبال الرسائل من فيسبوك ماسنجر والرد عليها باستخدام ChatGPT"""
    data = request.get_json()
    print("📩 Received:", data)

    for entry in data.get("entry", []):
        for messaging in entry.get("messaging", []):
            sender_id = messaging["sender"]["id"]
            if "message" in messaging and "text" in messaging["message"]:
                message_text = messaging["message"]["text"]
                response_text = chat_with_gpt(message_text)
                send_message(sender_id, response_text)

    return jsonify({"status": "Message received"}), 200

def send_message(recipient_id, text):
    """إرسال رد إلى فيسبوك ماسنجر"""
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, json=payload)
    print("📤 Sent:", text, "Status:", response.status_code)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
