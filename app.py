import os
import requests
import logging
from flask import Flask, request
from datetime import datetime
from openai import OpenAI

# إعدادات logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)

# مفاتيح البيئة
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client_openai = OpenAI(api_key=OPENAI_API_KEY)

# إرسال رسالة

def send_message(sender_id, text):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": sender_id},
        "message": {"text": text}
    }
    requests.post(url, json=payload)

# البحث عن زبون

def search_client(messenger_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/clients"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    params = {"filterByFormula": f"Messenger_ID='{messenger_id}'"}
    response = requests.get(url, headers=headers, params=params)
    logging.debug("🔍 Search client response: %s", response.text)
    data = response.json()
    return data['records'][0] if data.get('records') else None

# إنشاء زبون جديد

def create_client(messenger_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/clients"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "fields": {
            "Messenger_ID": messenger_id,
            "Date Inscription": datetime.now().isoformat()
        }
    }
    response = requests.post(url, headers=headers, json=data)
    logging.error("🆕 Airtable response (create): %s", response.text)
    return response.json() if response.status_code == 200 else None

# تحديث حقل ما

def update_client(record_id, fields):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/clients/{record_id}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    requests.patch(url, headers=headers, json={"fields": fields})

# تحليل رقم الهاتف

def is_valid_phone(text):
    try:
        response = client_openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": f"هل هذا رقم هاتف جزائري صالح؟ جاوب بنعم أو لا: {text}"}]
        )
        return "نعم" in response.choices[0].message.content
    except:
        return False

# نقطة الويبهوك
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    event = data["entry"][0]["messaging"][0]
    sender_id = event["sender"]["id"]

    # قراءة النص
    user_text = event["message"].get("text", "").strip()
    if not user_text:
        send_message(sender_id, "بعتلنا المعلومات كتابة فقط من فضلك.")
        return "ok"

    # تسجيل مستعمل
    client = search_client(sender_id)
    if not client:
        client = create_client(sender_id)
        if not client:
            send_message(sender_id, "🙏 وقع مشكل تقني صغير، جرب بعد لحظات")
            return "ok"
        else:
            send_message(sender_id, "مرحبا بيك في متجر الأحذية تاعنا. أرسل لنا رمز المنتج باش نكملو الطلب.")
            return "ok"

    record_id = client["id"]
    fields = client.get("fields", {})

    if not fields.get("Code Produit"):
        update_client(record_id, {"Code Produit": user_text})
        send_message(sender_id, "جيد، أعطينا رقم هاتفك باش نتواصلو معاك.")
        return "ok"

    if not fields.get("Téléphone"):
        if is_valid_phone(user_text):
            update_client(record_id, {"Téléphone": user_text})
            send_message(sender_id, "ممتاز! الآن أعطينا عنوان التوصيل.")
        else:
            send_message(sender_id, "الرقم يبدو غير صحيح، من فضلك عاود أرسله.")
        return "ok"

    if not fields.get("Adresse Livraison"):
        update_client(record_id, {"Adresse Livraison": user_text})
        send_message(sender_id, "شكرا! سجلنا الطلب بنجاح وراح نتواصلو معاك قريب.")
        return "ok"

    return "ok"

# تشغيل التطبيق
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))











