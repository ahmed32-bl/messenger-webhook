from flask import Flask, request, jsonify

app = Flask(__name__)

# رمز التحقق (يجب أن يكون نفسه الذي أدخلته في Facebook Webhook)
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
    """ استقبال رسائل من Messenger """
    data = request.get_json()
    print("📩 Received:", data)

    return jsonify({"status": "Message received"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
