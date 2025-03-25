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

# تحليل الرد باستخدام GPT للتحقق من مناسبة الرد
def analyze_response(prompt, text):
    response = client_openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": f"{prompt}: {text}"}]
    )
    return response.choices[0].message.content.strip()

# البحث عن المستخدم بواسطة Messenger ID
def search_client(messenger_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Clients"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    params = {"filterByFormula": f"Messenger_ID='{messenger_id}'"}
    resp = requests.get(url, headers=headers, params=params).json()
    return resp['records'][0] if resp['records'] else None

# إنشاء سجل جديد للزبون
def create_client(messenger_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Clients"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    data = {"fields": {"Messenger_ID": messenger_id, "Date Inscription": datetime.now().isoformat()}}
    resp = requests.post(url, headers=headers, json=data).json()
    return resp

# تحديث بيانات الزبون في الجدول
def update_client(record_id, fields):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Clients/{record_id}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    requests.patch(url, headers=headers, json={"fields": fields})

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

    if not fields.get("Code Produit"):
        code_produit = event["message"].get("text")
        valid_code = analyze_response("هل هذا النص يمثل رمز منتج؟", code_produit)
        if "نعم" in valid_code:
            update_client(client["id"], {"Code Produit": code_produit})
            send_message(sender_id, "جيد، أعطينا رقم هاتفك باش نتواصلو معاك.")
        else:
            send_message(sender_id, "الرجاء التأكد من إرسال رمز المنتج الصحيح.")

    elif not fields.get("Téléphone"):
        phone = event["message"].get("text")
        valid_phone = analyze_response("هل هذا النص يمثل رقم هاتف جزائري صالح؟", phone)
        if "نعم" in valid_phone:
            update_client(client["id"], {"Téléphone": phone})
            send_message(sender_id, "ممتاز! الآن أعطينا عنوان التوصيل.")
        else:
            send_message(sender_id, "الرقم يبدو غير صحيح، من فضلك عاود أرسله.")

    elif not fields.get("Adresse Livraison"):
        address = event["message"].get("text")
        update_client(client["id"], {"Adresse Livraison": address})
        send_message(sender_id, "شكرا! سجلنا الطلب بنجاح وراح نتواصلو معاك قريب.")

    new_conversation = conversation + f"\n[{datetime.now()}] {event['message'].get('text', 'رسالة')}"
    update_client(client["id"], {"Conversation": new_conversation})

    return "ok"

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))







