import os
import requests
from flask import Flask, request
from datetime import datetime
from openai import OpenAI

app = Flask(__name__)

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client_openai = OpenAI(api_key=OPENAI_API_KEY)

# إرسال رسالة عبر Messenger
def send_message(sender_id, text):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": sender_id}, "message": {"text": text}}
    requests.post(url, json=payload)

# تحليل الرد باستخدام GPT
def analyze_response(prompt, text):
    response = client_openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": f"{prompt}: {text}"}]
    )
    return response.choices[0].message.content.strip()

# البحث عن المستخدم في Airtable
def search_client(messenger_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Clients"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    params = {"filterByFormula": f"Messenger_ID='{messenger_id}'"}
    resp = requests.get(url, headers=headers, params=params).json()
    return resp['records'][0] if resp['records'] else None

# إنشاء سجل جديد
def create_client(messenger_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Clients"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    data = {"fields": {"Messenger_ID": messenger_id, "Date Inscription": datetime.now().isoformat()}}
    resp = requests.post(url, headers=headers, json=data).json()
    return resp

# تحديث بيانات العميل
def update_client(record_id, fields):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Clients/{record_id}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    requests.patch(url, headers=headers, json={"fields": fields})

# محاولة الرد على سؤال عام من جدول Infos_Magasin
def try_answer_general_question(user_text):
    intent = analyze_response("هل هذا النص عبارة عن سؤال عام عن الأسعار أو التوصيل أو طرق الدفع؟ أجب فقط بنعم أو لا", user_text)
    if "نعم" not in intent:
        return None

    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Infos_Magasin"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    response = requests.get(url, headers=headers).json()

    for record in response.get("records", []):
        question_keywords = record["fields"].get("Question", "").lower()
        if any(word in user_text.lower() for word in question_keywords.split()):
            return record["fields"].get("Réponse")

    return "ما نقدرش نجاوبك بدقة، المسؤول راح يتواصل معاك ويوضحلك كل التفاصيل إن شاء الله."

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    event = data["entry"][0]["messaging"][0]
    sender_id = event["sender"]["id"]

    client = search_client(sender_id)
    if not client:
        client = create_client(sender_id)
        send_message(sender_id, "مرحبا بيك في متجر الأحذية تاعنا. أرسل لنا رمز المنتج باش نكملو الطلب.")
        return "ok"

    fields = client.get("fields", {})
    conversation = fields.get("Conversation", "")

    # التحقق من وجود مرفقات (صورة، صوت، فيديو)
    if "attachments" in event["message"]:
        send_message(sender_id, "معليش، ما نقدرش نقرا الصوت ولا الصور ولا الفيديوهات. بعتلنا المعلومات كتابة فقط.")
        new_conversation = conversation + f"\n[{datetime.now()}] (مرفق غير مدعوم)"
        update_client(client["id"], {"Conversation": new_conversation})
        return "ok"

    # متابعة المحادثة النصية
    user_text = event["message"].get("text", "").strip()
    if not user_text:
        send_message(sender_id, "بعتلنا المعلومات كتابة فقط من فضلك.")
        return "ok"

    # محاولة الرد على سؤال عام
    if not fields.get("Code Produit"):
        general_answer = try_answer_general_question(user_text)
        if general_answer:
            send_message(sender_id, general_answer)
            send_message(sender_id, "أرسل لنا رمز المنتج باش نكملو الطلب.")
            return "ok"

    # جمع البيانات المعتادة
    if not fields.get("Code Produit"):
        code_produit = user_text
        valid_code = analyze_response("هل هذا النص يمثل رمز منتج؟", code_produit)
        if "نعم" in valid_code:
            update_client(client["id"], {"Code Produit": code_produit})
            send_message(sender_id, "جيد، أعطينا رقم هاتفك باش نتواصلو معاك.")
        else:
            send_message(sender_id, "الرجاء التأكد من إرسال رمز المنتج الصحيح.")

    elif not fields.get("Téléphone"):
        phone = user_text
        valid_phone = analyze_response("هل هذا النص يمثل رقم هاتف جزائري صالح؟", phone)
        if "نعم" in valid_phone:
            update_client(client["id"], {"Téléphone": phone})
            send_message(sender_id, "ممتاز! الآن أعطينا عنوان التوصيل.")
        else:
            send_message(sender_id, "الرقم يبدو غير صحيح، من فضلك عاود أرسله.")

    elif not fields.get("Adresse Livraison"):
        address = user_text
        update_client(client["id"], {"Adresse Livraison": address})
        send_message(sender_id, "شكرا! سجلنا الطلب بنجاح وراح نتواصلو معاك قريب.")

    # تسجيل كل شيء في Conversation
    new_conversation = conversation + f"\n[{datetime.now()}] {user_text}"
    update_client(client["id"], {"Conversation": new_conversation})

    return "ok"

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))








