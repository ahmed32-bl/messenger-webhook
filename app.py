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
        "message": {"text": "\u200F" + text}
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

def gpt_analyze(step, user_text, history, infos, user_fields):
    try:
        prompt = f"""
        السياق العام:
        أنت مساعد ذكي يعمل لصالح متجر سراويل جزائري. هدفك هو مساعدة الزبائن خلال محادثة على فيسبوك مسنجر من أجل جمع معلومات الطلب، والإجابة على استفساراتهم بشكل دقيق، واضح واحترافي.

        كل رسالة يتم إرسالها إليك على شكل دفعة جديدة، لذلك تحتاج في كل مرة إلى:
        - مراجعة سجل المحادثة الكامل.
        - مراجعة المعلومات المتوفرة عن الزبون.
        - مراجعة معلومات المتجر.
        - تحليل الرسالة الجديدة من الزبون.
        - فهم نيته ومقصد كلامه بدقة.
        - ثم بعد ذلك، تولد إجابة ذكية مبنية على السياق الكامل.

        المرحلة الحالية من التسجيل: {step}

        هذا هو سجل المحادثة الكامل مع هذا الزبون:
        {history}

        هذه هي الرسالة الجديدة من الزبون:
        "{user_text}"

        هذه هي المعلومات التي جمعناها لحد الآن من الزبون:
        {user_fields}

        هذه هي معلومات المتجر:
        {infos}

        خطوات العمل:
        1. حلل نية الزبون من الرسالة الجديدة (هل يجاوب؟ هل يسأل؟ هل يغير موضوع؟...)
        2. راجع المعلومات أعلاه بالكامل.
        3. إذا كانت الرسالة مناسبة للمرحلة الحالية، جاوب في السطر الأول فقط بـ: "نعم"
        4. بعدها أضف شرحك وتحليلك الكامل إذا لزم.
        5. إذا كانت استفسار عن منتج أو توصيل، جاوب بدارجة جزائرية.
        6. إذا كانت غير مفهومة أو خارجة على السياق، جاوب: "ما فهمتش، واش تقصد؟"
        7. لا تعاود تطرح أسئلة، لا تفترض معلومات.
        ما تقولش واش راك تخمم فالمحادثة جاوب مباشرة كيما انسان عادي ماشي كيما روبو
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

        response_intro = f"""أهلا وسهلا بيك!
أنا هنا نعاونك باش نكملو الطلب تاعك خطوة بخطوة.
باش نقدر نعاونك، نبداو نجمع بعض المعلومات البسيطة:
- أول حاجة نحتاجو رمز السروال لي عجبك (مثلاً 07).
- ومن بعد نكملو برقم الهاتف والعنوان.

رسالتك الأولى كانت: \"{user_text}\"
نراجعها ونشوف وش نقدرو نديرو بها مباشرة."""
        send_message(sender_id, response_intro)
        return "ok"

    record_id = client["id"]
    fields = client.get("fields", {})
    log_conversation(record_id, user_text)

    history = fields.get("Conversation", "")
    infos = get_infos_magasin()

    user_fields = ""
    for k, v in fields.items():
        if k in ["Code Produit", "Téléphone", "Adresse Livraison"]:
            user_fields += f"{k}: {v}\n"

    if not fields.get("Code Produit"):
        response = gpt_analyze("رمز المنتج", user_text, history, infos, user_fields)
        if response.startswith("نعم"):
            update_client(record_id, {"Code Produit": user_text})
            send_message(sender_id, "سجلنا الرمز، بعتلنا رقم هاتفك.")
        elif response.startswith("ما فهمتش"):
            send_message(sender_id, response)
        else:
            send_message(sender_id, response + "\nلكن نحتاج رمز المنتج باش نكملو.")
        return "ok"

    if not fields.get("Téléphone"):
        response = gpt_analyze("رقم الهاتف", user_text, history, infos, user_fields)
        if response.startswith("نعم"):
            update_client(record_id, {"Téléphone": user_text})
            send_message(sender_id, "تمام! دوك بعتلنا عنوان التوصيل.")
        elif response.startswith("ما فهمتش"):
            send_message(sender_id, response)
        else:
            send_message(sender_id, response + "\nلكن نحتاج رقم الهاتف باش نكملو.")
        return "ok"

    if not fields.get("Adresse Livraison"):
        response = gpt_analyze("العنوان", user_text, history, infos, user_fields)
        if response.startswith("نعم"):
            update_client(record_id, {"Adresse Livraison": user_text})
            send_message(sender_id, "شكراً! سجلنا كلش، وراح نتواصلو معاك قريباً.")
        elif response.startswith("ما فهمتش"):
            send_message(sender_id, response)
        else:
            send_message(sender_id, response + "\nلكن نحتاج عنوان التوصيل باش نكملو.")
        return "ok"

    response = gpt_analyze("تم التسجيل", user_text, history, infos, user_fields)
    send_message(sender_id, response)
    return "ok"


# -------------------- التحقق من Facebook Webhook --------------------

@app.route("/webhook", methods=["GET"])
def verify():
    verify_token = "warcha123"  # لازم يكون نفس اللي تدخله في إعدادات Facebook
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == verify_token:
        return challenge, 200
    return "Verification token mismatch", 403

# -------------------- الصفحة الرئيسية (اختياري) --------------------

@app.route("/", methods=["GET"])
def home():
    return "✅ Webhook is running!"


# -------------------- تشغيل --------------------

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))


