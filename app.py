import os
import requests
import logging
from flask import Flask, request
from datetime import datetime
import pytz
from openai import OpenAI

logging.basicConfig(level=logging.DEBUG)
app = Flask(__name__)

# ==================== إعداد المتغيرات البيئية ====================

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client_openai = OpenAI(api_key=OPENAI_API_KEY)

# ==================== دالة إرسال الرسائل عبر Messenger ====================

def send_message(sender_id, text):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": sender_id},
        "message": {"text": "\u200F" + text}  # \u200F لمعالجة اتجاه النص
    }
    requests.post(url, json=payload)

# ==================== دوال للتعامل مع Airtable ====================

import json

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

# ==================== دالة لجلب معلومات المتجر من Infos_Magasin ====================

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

# ==================== دالة الذكاء الاصطناعي (GPT) ====================

def gpt_analyze(step, user_text, history, infos, user_fields):
    try:
        prompt = f"""
أنت مساعد ذكي مستدعى عبر API في بوت Messenger لمتجر سراويل العيد في وهران. 
دورك: ترد على الزبائن بلهجة دارجة جزائرية واضحة ومختصرة، وتساعدهم يشرو السروال. 
كل رسالة تجيك فيها:

- سجل المحادثة: {history}
- الرسالة الجديدة: "{user_text}"
- معلومات المتجر: {infos}
- معلومات الزبون: {user_fields}
- المرحلة الحالية: {step}

مواصفات المتجر والسروال:
- نفس الموديل (قماش متين، خياطة متقونة)
- مقاسات: L / XL / XXL
- ألوان برموز مختلفة (1 لـ الأسود، 2 لـ الرمادي داكن... إلخ)
- السعر: 170 ألف للسروال، زوج سراويل بـ 300 ألف
- التوصيل مجاني وفوري في وهران فقط
- الدفع عند الاستلام بعد ما يشوف الزبون السروال
- لا يوجد إرجاع أو تبديل بعد الدفع

تعليمات الرد:
1. جاوب بدارجة جزائرية مفهومة، دون تفاصيل تقنية عن الكود أو الـAPI.
2. إذا كان السؤال عن السعر، التوصيل، المقاسات... جاوب بالمعلومات المعروفة.
3. إذا كان مناسب للمرحلة (جمع Code Produit، Taille، Quantité، Téléphone، Adresse)، جاوب أولاً بـ "نعم" في سطر إذا كان الزبون عطاك المعلومة المطلوبة.
4. إذا ما فهمتش سؤاله، قل: "ما فهمتش، واش تقصد؟"
5. متطولش: رد في سطر أو سطرين، بلا شرح داخلي.

ردك الآن؟
        """
        response = client_openai.chat.completions.create(
            model="gpt-4",  # أو gpt-3.5-turbo لو ماعندكش GPT-4
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"GPT error: {e}")
        return "ما فهمتش، واش تقصد؟"

# ==================== Webhook POST (الرسائل) ====================

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    event = data["entry"][0]["messaging"][0]
    sender_id = event["sender"]["id"]

    user_text = event["message"].get("text", "").strip() if "message" in event else ""
    if not user_text:
        send_message(sender_id, "✍️ بعتلنا الكتابة فقط من فضلك.")
        return "ok"

    # ابحث عن العميل في Airtable
    client = search_client(sender_id)
    if not client:
        # عميل جديد -> إنشاء سجل
        client = create_client(sender_id)
        if not client:
            # خطأ في الإنشاء
            send_message(sender_id, "🔴 وقع مشكل تقني، جرب بعد لحظات.")
            return "ok"

        # رسالة ترحيبية أولى
        response_intro = f"""سلام خويا، مرحبا بيك!
راح نعاونك خطوة بخطوة باش تطلب السروال لي عجبك.
أول حاجة نحتاجو منك رقم اللون (Code Produit) باش نسجلو الطلب.
"""
        send_message(sender_id, response_intro)
        return "ok"

    # إذا وصلنا هنا معناه العميل موجود في Airtable
    record_id = client["id"]
    fields = client.get("fields", {})

    # سجل المحادثة
    log_conversation(record_id, user_text)

    # حضر المعلومات لتمريرها لـ GPT
    history = fields.get("Conversation", "")
    infos = get_infos_magasin()

    # نجمع بيانات مهمة من سجل الزبون لعرضها لـ GPT
    user_fields = ""
    relevant_keys = ["Code Produit", "Taille", "Quantité", "Téléphone", "Adresse Livraison"]
    for k in relevant_keys:
        if k in fields:
            user_fields += f"{k}: {fields[k]}\n"

    # ========== منطق جمع البيانات حسب الترتيب ==========

    # 1. Code Produit
    if not fields.get("Code Produit"):
        response = gpt_analyze("جمع Code Produit", user_text, history, infos, user_fields)
        if response.startswith("نعم"):
            update_client(record_id, {"Code Produit": user_text})
            send_message(sender_id, "سجلنا اللون. واش هو المقاس لي حابو؟ (L/XL/XXL)")
        elif response.startswith("ما فهمتش"):
            send_message(sender_id, response)
        else:
            send_message(sender_id, response + "\nنحتاج رقم لون السروال (Code Produit).")
        return "ok"

    # 2. Taille (المقاس)
    if not fields.get("Taille"):
        response = gpt_analyze("جمع Taille", user_text, history, infos, user_fields)
        if response.startswith("نعم"):
            update_client(record_id, {"Taille": user_text})
            send_message(sender_id, "سجلنا المقاس. قدّاه عدد السراويل لي تحب تطلبهم؟")
        elif response.startswith("ما فهمتش"):
            send_message(sender_id, response)
        else:
            send_message(sender_id, response + "\nنحتاج المقاس: L/XL/XXL.")
        return "ok"

    # 3. Quantité (عدد القطع)
    if not fields.get("Quantité"):
        response = gpt_analyze("جمع Quantité", user_text, history, infos, user_fields)
        if response.startswith("نعم"):
            update_client(record_id, {"Quantité": user_text})
            send_message(sender_id, "تمام! بعتلنا رقم الهاتف من فضلك.")
        elif response.startswith("ما فهمتش"):
            send_message(sender_id, response)
        else:
            send_message(sender_id, response + "\nنحتاج عدد السراويل (1 أو 2 أو أكثر).")
        return "ok"

    # 4. Téléphone
    if not fields.get("Téléphone"):
        response = gpt_analyze("جمع Téléphone", user_text, history, infos, user_fields)
        if response.startswith("نعم"):
            update_client(record_id, {"Téléphone": user_text})
            send_message(sender_id, "شكرًا! دير العنوان بالضبط (في وهران) باش نوصّلوه.")
        elif response.startswith("ما فهمتش"):
            send_message(sender_id, response)
        else:
            send_message(sender_id, response + "\nنحتاج رقم الهاتف باش نتواصل.")
        return "ok"

    # 5. Adresse Livraison
    if not fields.get("Adresse Livraison"):
        response = gpt_analyze("جمع Adresse Livraison", user_text, history, infos, user_fields)
        if response.startswith("نعم"):
            update_client(record_id, {"Adresse Livraison": user_text})
            send_message(sender_id, "شكراً خويا! سجلنا كلش، قريب نتواصلو معاك باش نكملو الطلب.")
        elif response.startswith("ما فهمتش"):
            send_message(sender_id, response)
        else:
            send_message(sender_id, response + "\nنحتاج العنوان باش نخدمو التوصيل في وهران.")
        return "ok"

    # إذا راه جمع كل البيانات، راه مسجّل كامل
    response = gpt_analyze("تم التسجيل", user_text, history, infos, user_fields)
    send_message(sender_id, response)
    return "ok"

# ==================== Webhook GET (للتحقق من فيسبوك) ====================

@app.route("/webhook", methods=["GET"])
def verify():
    verify_token = "warcha123"  # نفس التوكن في إعدادات فيسبوك
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == verify_token:
        return challenge, 200
    return "Verification token mismatch", 403

# ==================== صفحة رئيسية (اختياري) ====================

@app.route("/", methods=["GET"])
def home():
    return "✅ Webhook is running!"

# ==================== تشغيل التطبيق ====================
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))



