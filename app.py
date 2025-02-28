import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# التوكن للتحقق من فيسبوك
VERIFY_TOKEN = "workshop_chatbot_123"  # تأكد من أنه نفس التوكن في إعدادات فيسبوك

# توكن الوصول إلى صفحة ماسنجر
PAGE_ACCESS_TOKEN = "EAANEgEzn4hwBOwxeBNDM0YR3SB952FCzpSsOurktbYtAbAI6beIwrK8WhZCtgYDP1HNJmOGD97zqV6NAlxucnZABI7C58PqNERdZArL6O4P0NYHYhuwZAPQX8vvCyhQKQTUTyeBYI4tymgkxwz6Xw9HDeibYBMUSdeR4rREcr9fBT3ZAbrujogdIvFBBJXnKJJbryoREMrHeOZAGJ8zQZDZD"  

# API Key الخاصة بـ OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def chat_with_gpt(message):
    """إرسال الرسائل إلى ChatGPT والرد على المستخدم"""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": message}]
    }
    
    response = requests.post(url, headers=headers, json=payload)
    response_data = response.json()

    if "choices" in response_data:
        return response_data["choices"][0]["message"]["content"]
    else:
        return "❌ حدث خطأ في الاتصال بـ ChatGPT."

@app.route("/", methods=["GET"])
def home():
    return "Messenger Webhook is running!"

@app.route("/webhook", methods=["GET"])
def verify():
    """ التحقق من Webhook في فيسبوك"""
    token_sent = request.args.get("hub.verify_token")
    if token_sent == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Invalid verification token", 403

@app.route("/webhook", methods=["POST"])
def receive_message():
    """استقبال الرسائل من ماسنجر والرد باستخدام ChatGPT"""
    data = request.get_json()
    print("📩 Received:", data)

    if "entry" in data and len(data["entry"]) > 0:
        messaging = data["entry"][0].get("messaging", [])
        for event in messaging:
            if "message" in event:
                sender_id = event["sender"]["id"]
                message_text = event["message"].get("text", "")

                # إرسال النص إلى ChatGPT والحصول على الرد
                bot_response = chat_with_gpt(message_text)
                send_message(sender_id, bot_response)

    return "Message processed", 200

def send_message(recipient_id, text):
    """إرسال رسالة إلى المستخدم على ماسنجر"""
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    
    response = requests.post(url, headers=headers, json=payload)
    print("📤 Sent:", text, "Status:", response.status_code)
    return response.json()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
