import os
import requests
import logging
from flask import Flask, request
from datetime import datetime, timedelta
import pytz
from openai import OpenAI

logging.basicConfig(level=logging.DEBUG)
app = Flask(__name__)

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client_openai = OpenAI(api_key=OPENAI_API_KEY)

# -------------------- أدوات أساسية --------------------

def send_message(sender_id, text):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": sender_id},
        "message": {"text": text}
    }
    requests.post(url, json=payload)

# -------------------- Airtable --------------------

def search_client(messenger_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/clients"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    params = {"filterByFormula": f"Messenger_ID='{messenger_id}'"}
    response = requests.get(url, headers=headers, params=params)
    logging.debug("🔍 Search client response: %s", response.text)
    data = response.json()
    return data['records'][0] if data.get('records') else None

def create_client(messenger_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/clients"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    # توقيت الجزائر
    alg_time = datetime.now(pytz.timezone("Africa/Algiers")).strftime("%Y-%m-%dT%H:%M:%S")
    data = {
        "fields": {
            "Messenger_ID": messenger_id,
            "Date Inscription": alg_time
        }
    }
    response = requests.post(url, headers=headers, json=data)
    logging.error("🆕 Airtable response (create): %s", response.text)
    if response.status_code in [200, 201]:
        return response.json()
    else:
        return None

def update_client(record_id, fields):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/clients/{record_id}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.patch(url, headers=headers, json={"fields": fields})
    logging.debug("✏️ Update client response: %s", response.text)

def search_client_by_id(record_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/clients/{record_id}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    response = requests.get(url, headers=headers)
    return response.json()

def log_conversation(record_id, message):
    client = search_client_by_id(record_id)
    old_convo = client.get("fields", {}).get("Conversation", "")
    new_convo = f"{old_convo}\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {message}"
    update_client(record_id, {"Conversation": new_convo})

# -------------------- GPT تحليل --------------------

def is_valid_phone(text):
    try:
        response = client_openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": f"هل هذا رقم هاتف جزائري صالح؟ جاوب بنعم أو لا: {text}"}]
        )
        return "نعم" in response.choices[0].message.content
    except:
        return False

def is_answer_relevant(step, user_text):
    try:
        prompt = f"""
        أنت مساعد افتراضي تسجل معلومات زبون طلب منتج. المرحلة الحالية هي: {step}.
        الزبون كتب: \"{user_text}\"
        هل هذا الجواب مناسب لهذه المرحلة؟

        جاوب فقط بـ \"نعم\" أو \"لا\".
        """
        response = client_openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        return "نعم" in response.choices[0].message.content
    except:
        return True

def detect_question_type(user_text):
    try:
        prompt = f"""
        أنت مساعد افتراضي تفهم رسائل الزبائن.
        الرسالة: \"{user_text}\"

        هل هذه الرسالة:
        1. تحتوي على معلومات مثل رقم أو عنوان أو رمز منتج؟
        2. أو أنها سؤال عن منتج، سعر، توصيل...؟
        3. أو أنها غير مفهومة؟

        جاوب فقط بـ:
        - \"معلومة\"
        - \"سؤال\"
        - \"غير واضح\"
        """
        response = client_openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except:
        return "غير واضح"

# -------------------- جدول Infos_Magasin --------------------

def search_in_infos(user_text):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Infos_Magasin"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    response = requests.get(url, headers=headers)
    records = response.json().get("records", [])

    for record in records:
        question = record["fields"].get("Question", "").lower()
        answer = record["fields"].get("Réponse", "")
        if question in user_text.lower():
            return answer
    return None

# -------------------- Webhook --------------------

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    event = data["entry"][0]["messaging"][0]
    sender_id = event["sender"]["id"]
    user_text = event["message"].get("text", "").strip()

    if not user_text:
        send_message(sender_id, "بعتلنا المعلومات كتابة فقط من فضلك.")
        return "ok"

    client = search_client(sender_id)
    if not client:
        client = create_client(sender_id)
        if not client:
            send_message(sender_id, "🔴 وقع مشكل تقني، جرب بعد لحظات.")
            return "ok"
        send_message(sender_id, "مرحبا بيك في متجر الأحذية تاعنا 👟 أرسل رمز المنتج باش نكملو الطلب.")
        return "ok"

    record_id = client["id"]
    fields = client.get("fields", {})

    log_conversation(record_id, user_text)
    kind = detect_question_type(user_text)

    if kind == "سؤال":
        answer = search_in_infos(user_text)
        send_message(sender_id, answer or "🔎 خليني نشوف ونجاوبك إن شاء الله.")
        return "ok"

    if not fields.get("Code Produit"):
        if is_answer_relevant("رمز المنتج", user_text):
            update_client(record_id, {"Code Produit": user_text})
            send_message(sender_id, "جيد ✅ أرسل رقم هاتفك باش نتواصلو معاك.")
        else:
            send_message(sender_id, "📌 نحتاج رمز المنتج لي راه على الصورة (مثلاً: 1123). بعتلي الرمز باش نكملو.")
        return "ok"

    if not fields.get("Téléphone"):
        if is_answer_relevant("رقم الهاتف", user_text):
            if is_valid_phone(user_text):
                update_client(record_id, {"Téléphone": user_text})
                send_message(sender_id, "ممتاز 👍 الآن أرسل عنوان التوصيل.")
            else:
                send_message(sender_id, "❌ الرقم غير صحيح. حاول تبعت رقم جزائري يبدأ بـ 05 أو 06 أو 07.")
        else:
            send_message(sender_id, "👀 راني نستنى رقم الهاتف، بعتلي رقم باش نكملو.")
        return "ok"

    if not fields.get("Adresse Livraison"):
        if is_answer_relevant("عنوان التوصيل", user_text):
            update_client(record_id, {"Adresse Livraison": user_text})
            send_message(sender_id, "📦 شكرا! سجلنا الطلب وسنتواصل معاك قريبًا إن شاء الله.")
        else:
            send_message(sender_id, "📍 أرسل العنوان الكامل (المدينة + الحي)، باش نوصلولك الطلب.")
        return "ok"

    send_message(sender_id, "✅ إذا تحب تستفسر على شي آخر، راني هنا.")
    return "ok"

# -------------------- تشغيل --------------------

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
