import os
import requests
from flask import Flask, request, jsonify
import openai
from dotenv import load_dotenv

# إذا كنت لا تستخدم .env محليًا، يمكنك إزالة السطرين التاليين:
load_dotenv()

app = Flask(__name__)

# =============================
# إعداد متغيرات البيئة
# =============================
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")  # personal access token
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

# اسم الجداول في Airtable
TABLE_MESSAGES = "Messages"
TABLE_SUMMARIES = "Summaries"

# =============================
# إعداد مفتاح OpenAI
# =============================
openai.api_key = OPENAI_API_KEY

########################################
# نقطة النهاية للتحقق من Webhook
########################################
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    token_sent = request.args.get("hub.verify_token")
    if token_sent == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Unauthorized", 403

########################################
# استقبال الرسائل من ماسنجر
########################################
@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for message_event in entry.get("messaging", []):
                sender_id = message_event.get("sender", {}).get("id")
                if message_event.get("message"):
                    message_text = message_event["message"].get("text")

                    # جلب آخر 5 رسائل + الملخص
                    previous_messages = get_previous_messages(sender_id)
                    summary = get_summary(sender_id)

                    # توليد الرد بواسطة OpenAI (افتراضي gpt-3.5-turbo)
                    response_text = process_message(
                        user_id=sender_id,
                        message_text=message_text,
                        previous_messages=previous_messages,
                        summary=summary,
                        model_name="gpt-4"  # يمكن تغييره لاحقًا إلى gpt-4
                    )

                    # إرسال الرد للمستخدم
                    send_message(sender_id, response_text)

                    # حفظ رسالة المستخدم
                    save_message(sender_id, message_text, "user")
                    # حفظ رد البوت
                    save_message(sender_id, response_text, "bot")

                    # تحديث الملخص إذا تجاوز 10 رسائل
                    update_summary(sender_id)
    return "OK", 200

########################################
# استرجاع المحادثات السابقة من Airtable
########################################
def get_previous_messages(user_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_MESSAGES}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        records = response.json().get("records", [])
        messages_list = []
        for record in records:
            fields = record.get("fields", {})
            if fields.get("user_id") == user_id:
                # تأكّد من وجود 'message'
                msg_text = fields.get("message")
                if msg_text is not None:
                    messages_list.append(msg_text)
        return messages_list[-5:]  # آخر 5 رسائل فقط
    return []

########################################
# استرجاع الملخص من Airtable
########################################
def get_summary(user_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_SUMMARIES}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        records = response.json().get("records", [])
        for record in records:
            fields = record.get("fields", {})
            if fields.get("user_id") == user_id:
                return fields.get("summary", "")
    return ""

########################################
# تحديث الملخص في Airtable
########################################
def update_summary(user_id):
    # جلب جميع رسائل المستخدم
    all_messages = get_all_messages(user_id)
    if len(all_messages) >= 10:
        summary_text = summarize_conversation(all_messages)
        post_summary(user_id, summary_text)

########################################
# جلب جميع الرسائل للمستخدم
########################################
def get_all_messages(user_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_MESSAGES}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        records = response.json().get("records", [])
        messages_list = []
        for record in records:
            fields = record.get("fields", {})
            if fields.get("user_id") == user_id:
                msg_text = fields.get("message")
                if msg_text is not None:
                    messages_list.append(msg_text)
        return messages_list
    return []

########################################
# إرسال الملخص إلى Airtable
########################################
def post_summary(user_id, summary_text):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_SUMMARIES}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {"fields": {"user_id": user_id, "summary": summary_text}}
    requests.post(url, headers=headers, json=data)

########################################
# تلخيص المحادثة
########################################
def summarize_conversation(messages):
    summary_prompt = (
        "لخص المحادثة التالية بإيجاز دون فقدان المعلومات المهمة:\n"
        + "\n".join(messages)
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # يمكن تغييره إلى gpt-4
            messages=[{"role": "user", "content": summary_prompt}]
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("Summary Error:", e)
        return ""

########################################
# معالجة الرسائل باستخدام OpenAI
########################################
def process_message(user_id, message_text, previous_messages, summary, model_name="gpt-3.5-turbo"):
    try:
        messages = [
            {"role": "system", "content": "تذكر هذه المحادثة مع المستخدم"}
        ]
        if summary:
            messages.append({"role": "system", "content": f"ملخص المحادثة السابقة: {summary}"})
        for msg in previous_messages:
            messages.append({"role": "user", "content": msg})
        messages.append({"role": "user", "content": message_text})

        response = openai.ChatCompletion.create(
            model=model_name,
            messages=messages
        )
        return response["choices"][0]["message"].get("content", "").strip()
    except Exception as e:
        print("OpenAI Error:", e)
        print("=================== ERROR STACK TRACE ===================")
        return "عذرًا، حدث خطأ. حاول مرة أخرى لاحقًا."

########################################
# حفظ الرسالة في Airtable
########################################
def save_message(user_id, message_text, sender):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_MESSAGES}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {"fields": {"user_id": user_id, "message": message_text, "sender": sender}}
    requests.post(url, headers=headers, json=data)

########################################
# إرسال رسالة إلى ماسنجر
########################################
def send_message(recipient_id, message_text):
    url = "https://graph.facebook.com/v13.0/me/messages"
    headers = {"Content-Type": "application/json"}
    params = {"access_token": PAGE_ACCESS_TOKEN}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    requests.post(url, headers=headers, params=params, json=payload)

########################################
# نقطة البداية
########################################
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
