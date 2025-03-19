from flask import Flask, request, jsonify
import os
import logging
import requests

# إعداد سجل التتبع
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# تحميل المتغيرات البيئية من Render
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")

# إنشاء تطبيق Flask
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "Messenger Bot is running!", 200

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """ تحقق من الويب هوك عند الإعداد الأولي """
    token_sent = request.args.get("hub.verify_token")
    if token_sent == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "خطأ في التحقق", 403

@app.route("/webhook", methods=["POST"])
def handle_message():
    """ استقبال ومعالجة رسائل المستخدمين """
    try:
        data = request.get_json()
        sender_id = data['entry'][0]['messaging'][0]['sender']['id']
        message_text = data['entry'][0]['messaging'][0]['message']['text']

        logging.info(f"📩 استقبال رسالة من {sender_id}: {message_text}")

        # إرسال الرسالة إلى DeepSeek وتحليل الرد
        deepseek_url = "https://deepseek.api.url"  # استبدل بعنوان DeepSeek الحقيقي
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "message": message_text,
            "context": {"user_id": sender_id}
        }

        response = requests.post(deepseek_url, json=payload, headers=headers)
        response_data = response.json()
        bot_response = response_data.get("response", "عذرًا، ما قدرت نجاوبك.")

        # إرسال الرد إلى العميل
        send_message(sender_id, bot_response)
        return jsonify({"status": "success"})

    except Exception as e:
        logging.error(f"⚠️ خطأ أثناء معالجة الرسالة: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

# وظيفة إرسال الرسائل إلى العميل عبر Facebook Messenger API
def send_message(sender_id, message):
    url = f"https://graph.facebook.com/v11.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": sender_id},
        "message": {"text": message}
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        logging.error(f"⚠️ خطأ أثناء إرسال الرسالة: {response.text}")

if __name__ == "__main__":
    app.run(port=5000, debug=True)
