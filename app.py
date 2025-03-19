import os
import requests
import logging
from flask import Flask, request, jsonify
from openai import OpenAI

# إعداد سجل التتبع
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# تحميل المتغيرات البيئية
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")

# إعدادات DeepSeek
deepseek_url = "https://api.deepseek.com/v1/chat/completions"
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# إعداد تطبيق Flask
app = Flask(__name__)

@app.route("/webhook", methods=["GET"])
def verify():
    """ التحقق من توكن فيسبوك """
    token_sent = request.args.get("hub.verify_token")
    if token_sent == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Invalid verification token", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    """ استقبال ومعالجة رسائل المستخدم """
    try:
        data = request.get_json()
        for entry in data.get("entry", []):
            for message_data in entry.get("messaging", []):
                sender_id = message_data["sender"]["id"]
                if "message" in message_data:
                    user_message = message_data["message"].get("text", "")
                    logging.info(f"📩 رسالة من {sender_id}: {user_message}")
                    
                    # تحليل الرسالة عبر DeepSeek
                    bot_response = get_deepseek_response(user_message)
                    
                    # إرسال الرد إلى المستخدم
                    send_message(sender_id, bot_response)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error(f"⚠️ خطأ أثناء معالجة الطلب: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

def get_deepseek_response(user_message):
    """ إرسال رسالة إلى DeepSeek والحصول على الرد """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "انت مساعد ذكي للرد على استفسارات الزبائن بالدارجة الجزائرية."},
                {"role": "user", "content": user_message},
            ],
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"⚠️ خطأ عند الاتصال بـ DeepSeek: {str(e)}")
        return "عذراً، ما قدرت نجاوبك."

def send_message(recipient_id, message_text):
    """ إرسال رد إلى المستخدم عبر Facebook Messenger """
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {PAGE_ACCESS_TOKEN}"}
    payload = {"recipient": {"id": recipient_id}, "message": {"text": message_text}}
    response = requests.post("https://graph.facebook.com/v18.0/me/messages", headers=headers, json=payload)
    
    if response.status_code != 200:
        logging.error(f"⚠️ فشل إرسال الرسالة: {response.text}")

if __name__ == "__main__":
    app.run(port=5000, debug=True)

