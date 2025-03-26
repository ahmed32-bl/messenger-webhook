import os
import requests
import logging
from flask import Flask, request
from datetime import datetime
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

# -------------------- قراءة جدول Infos_Magasin --------------------

def get_infos_magasin():
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Infos_Magasin"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    response = requests.get(url, headers=headers)
    data = response.json().get("records", [])

    infos_text = ""
    for record in data:
        fields = record.get("fields", {})
        for key, value in fields.items():
            infos_text += f"{key}: {value}\n"
    return infos_text.strip()

# -------------------- GPT الذكاء --------------------

def gpt_analyze(step, user_text, history, infos):
    try:
        prompt = f"""
        أنت بوت تابع لمتجر أحذية. هدفك الرئيسي هو تسجيل معلومات الزبائن: رمز المنتج، رقم الهاتف، العنوان.
        الزبون راه في مرحلة: {step}.

        🧠 سجل المحادثة السابقة:
        {history}

        📩 الرسالة الجديدة:
        "{user_text}"

        📚 معلومات من المتجر:
        {infos}

        جاوب فقط:
        - إذا الرسالة تمثل فعلاً {step} قل: نعم
        - إذا كانت استفسار (مثلاً على السعر أو المقاس)، جاوب عليه بصيغة دارجة
        - إذا كانت غير مفهومة، قل: ما فهمتش، واش تقصد؟
        """
        response = client_openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"GPT error: {e}")
        return "ما فهمتش، واش تقصد؟"

# -------------------- Webhook --------------------

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    event = data["entry"][0]["messaging"][0]
    sender_id = event["sender"]["id"]
    user_text = event["message"].get("text", "").strip()

    if not user_text:
        send_message(sender_id, "✍️ بعتلنا الكتابة فقط من فضلك.")
        return "ok"

    client = search_client(sender_id)
    if not client:
        client = create_client(sender_id)
        if not client:
            send_message(sender_id, "🔴 وقع مشكل تقني، جرب بعد لحظات.")
            return "ok"
        send_message(sender_id, "👟 مرحبا بيك في متجر الأحذية تاعنا! بعتلنا رمز المنتج باش نبدأو.")
        return "ok"

    record_id = client["id"]
    fields = client.get("fields", {})
    log_conversation(record_id, user_text)

    # تحديث: قراءة حقيقية من جدول Infos_Magasin
    history = fields.get("Conversation", "")
    infos = get_infos_magasin()

    if not fields.get("Code Produit"):
        response = gpt_analyze("رمز المنتج", user_text, history, infos)
        if response.startswith("نعم"):
            update_client(record_id, {"Code Produit": user_text})
            send_message(sender_id, "✅ سجلنا الرمز، بعتلنا رقم هاتفك.")
        elif response.startswith("ما فهمتش"):
            send_message(sender_id, response)
        else:
            send_message(sender_id, response + "\nلكن نحتاج رمز المنتج باش نكملو.")
        return "ok"

    if not fields.get("Téléphone"):
        response = gpt_analyze("رقم الهاتف", user_text, history, infos)
        if response.startswith("نعم"):
            update_client(record_id, {"Téléphone": user_text})
            send_message(sender_id, "📞 تمام! دوك بعتلنا عنوان التوصيل.")
        elif response.startswith("ما فهمتش"):
            send_message(sender_id, response)
        else:
            send_message(sender_id, response + "\nلكن نحتاج رقم الهاتف باش نكملو.")
        return "ok"

    if not fields.get("Adresse Livraison"):
        response = gpt_analyze("العنوان", user_text, history, infos)
        if response.startswith("نعم"):
            update_client(record_id, {"Adresse Livraison": user_text})
            send_message(sender_id, "📦 شكراً! سجلنا كلش، وراح نتواصلو معاك قريباً.")
        elif response.startswith("ما فهمتش"):
            send_message(sender_id, response)
        else:
            send_message(sender_id, response + "\nلكن نحتاج عنوان التوصيل باش نكملو.")
        return "ok"

    send_message(sender_id, "✅ إذا تحب تسقسي على حاجة، راني هنا.")
    return "ok"

# -------------------- تشغيل --------------------

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

