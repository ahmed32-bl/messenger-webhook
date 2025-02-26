import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# استبدل هذا بالتوكن الخاص بالصفحة
PAGE_ACCESS_TOKEN = "YOUR_PAGE_ACCESS_TOKEN"

VERIFY_TOKEN = "workshop_chatbot_123"

@app.route("/", methods=["GET"])
def home():
    return "Messenger Webhook is running!"

@app.route("/webhook", methods=["GET"])
def verify():
    """ التحقق من Webhook """
    token_sent = request.args.get("hub.verify_token")
    if token_sent == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Invalid verification token", 403

@app.route("/webhook", methods=["POST"])
def receive_message():
    """ استقبال رسائل من Messenger والرد عليها """
    data = request.get_json()
    print("📩 Received:", data)

    # استخراج بيانات المرسل والرسالة
    if "entry" in data:
        for entry in data["entry"]:
            if "messaging" in entry:
                for message_event in entry["messaging"]:
                    sender_id = message_event["sender"]["id"]
                    if "message" in message_event:
                        message_text = message_event["message"].get("text", "")
                        send_message(sender_id, f"🤖 لقد تلقيت رسالتك: {message_text}")

    return jsonify({"status": "Message received"}), 200

def send_message(recipient_id, text):
    """ إرسال رد إلى المستخدم """
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    response = requests.post(url, json=payload, headers=headers)
    print(f"📤 Sent to {recipient_id}: {text}, Status: {response.status_code}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
