import os
import requests
import logging
from flask import Flask, request, jsonify
from datetime import datetime

# إعداد سجل التتبع
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# تحميل المتغيرات البيئية
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# إعداد أسماء الجداول
CONVERSATIONS_TABLE = "Conversations"
WORKERS_TABLE = "Liste_Couturiers"

# إعداد تطبيق Flask
app = Flask(__name__)

# 📌 قالب التفاعل مع DeepSeek
PROMPT_TEMPLATE = """
📌 باللهجة الجزائرية، وتجنب في جمع معلومات العمال دون الخروج عن الموضوع.
🔹 **ابدأ المحادثة بنجاح، حتى يستمتع كماسة معي.**
🔹 إذا كان **رجلاً**: اجمع بياناته كما هي.
🔹 إذا كانت **امرأة**: أطلب لها أن توفر رقم قريبها حتى نكمل العملية.
🔹 **اجمع المعلومات الأساسية فقط دون تفاصيل زائدة.**
🔹 اسأله **إذا سبق له خياطة سراويل**، ثم أطلب منه تحديد **نوع الملابس التي خيطها سابقًا**.
🔹 إذا لم يذكر نوع الملابس، **لا تستنتج شيئًا من نفسك**، واسأله مجددًا بطريقة لبقة.
🔹 تأكد من أن لديه **آلة دروات أو سورجي** فقط.
🔹 لا تتخطى هذه الأسئلة، وتجنب معلومات غير مطلوبة.
"""

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
                    process_message(sender_id, user_message)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error(f"⚠️ خطأ أثناء معالجة الطلب: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


def get_conversation_history(sender_id):
    """ استرجاع سجل المحادثات السابقة من Airtable """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{CONVERSATIONS_TABLE}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        records = response.json().get("records", [])
        for record in records:
            if record["fields"].get("Messenger_ID") == sender_id:
                return record  # يُعيد سجل المحادثة السابقة
    return None


def save_conversation(sender_id, user_message, bot_response):
    """ حفظ المحادثة في Airtable """
    conversation = get_conversation_history(sender_id)
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{CONVERSATIONS_TABLE}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    if conversation:
        record_id = conversation["id"]
        old_history = conversation["fields"].get("conversation_history", "")
        new_history = old_history + f"\n👤 المستخدم: {user_message}\n🤖 البوت: {bot_response}"
        data = {"fields": {
            "conversation_history": new_history,
            "Dernier_Message": user_message,
            "Date_Dernier_Contact": str(datetime.now().date())
        }}
        url_update = f"{url}/{record_id}"
        requests.patch(url_update, json=data, headers=headers)
    else:
        data = {"records": [{
            "fields": {
                "Messenger_ID": sender_id,
                "conversation_history": f"👤 المستخدم: {user_message}\n🤖 البوت: {bot_response}",
                "Dernier_Message": user_message,
                "Date_Dernier_Contact": str(datetime.now().date())
            }
        }]}
        requests.post(url, json=data, headers=headers)


def get_deepseek_response(prompt):
    """ إرسال الطلب إلى DeepSeek وتحليل الرد """
    url = "https://api.deepseek.com/your-endpoint"  # تأكد من وضع رابط API الصحيح
    headers = {
        "Authorization": f"Bearer {os.getenv('DEEPSEEK_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {"prompt": prompt, "max_tokens": 150}
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        return response.json().get("response", "⚠️ خطأ في تحليل الرد من DeepSeek")
    else:
        return "⚠️ حدث خطأ أثناء الاتصال بـ DeepSeek"


def process_message(sender_id, user_message):
    """ معالجة الرسالة الجديدة """
    conversation = get_conversation_history(sender_id)
    chat_history = ""
    if conversation and "fields" in conversation:
        chat_history = conversation["fields"].get("conversation_history", "")

    # 🔥 تحسين بناء prompt لضمان عدم وجود خطأ نصي
    prompt = (
        PROMPT_TEMPLATE
        + f"\n\n📜 **سياق سابق:**\n{chat_history}\n\n👤 **المستخدم:** {user_message}\n🤖 **البوت:**"
    )
    
    logging.info(f"📝 إرسال إلى DeepSeek: {prompt}")

    bot_response = get_deepseek_response(prompt)

    send_message(sender_id, bot_response)
    save_conversation(sender_id, user_message, bot_response)


def send_message(recipient_id, message_text):
    """ إرسال رد إلى المستخدم عبر Facebook Messenger """
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {PAGE_ACCESS_TOKEN}"}
    payload = {"recipient": {"id": recipient_id}, "message": {"text": message_text}}
    requests.post("https://graph.facebook.com/v18.0/me/messages", headers=headers, json=payload)


if __name__ == "__main__":
    app.run(port=5000, debug=True)



