import os
import requests
from flask import Flask, request, jsonify
import openai

# 📌 تهيئة التطبيق Flask
# هذا التطبيق يعمل كـ webhook للتفاعل مع Messenger
app = Flask(__name__)

# 📌 مفاتيح API والإعدادات
VERIFY_TOKEN = "workshop_chatbot_123"  # رمز التحقق من ال webhook مع Messenger
PAGE_ACCESS_TOKEN = "PAGE_ACCESS_TOKEN"  # مفتاح API لإرسال الرسائل عبر Messenger
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # مفتاح API لـ GPT-4
AIRTABLE_API_KEY = "AIRTABLE_API"  # مفتاح API لـ Airtable
AIRTABLE_BASE_ID = "AIRTABLE_BASE_ID"
TABLE_PRODUITS = "Produits"  # اسم جدول المنتجات
TABLE_COMMANDES = "Commandes"  # اسم جدول الطلبات
TABLE_CLIENTS = "Clients"  # اسم جدول العملاء
TABLE_FAQ = "FAQ"  # جدول الأسئلة الشائعة
ADMIN_ID = "503020996238881"  # معرف المسؤول لاستلام الإشعارات

# 🔹 التحقق من Webhook Messenger
@app.route("/webhook", methods=["GET"])
def verify():
    """ التحقق من صحة تكوين ال webhook مع Messenger """
    token_sent = request.args.get("hub.verify_token")
    if token_sent == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "رمز التحقق غير صحيح", 403

# 🔹 استقبال الرسائل والرد التلقائي
@app.route("/webhook", methods=["POST"])
def receive_message():
    """ استقبال رسائل العملاء من Messenger وإرسال الردود عبر الروبوت """
    data = request.json
    if data["object"] == "page":
        for entry in data["entry"]:
            for messaging_event in entry["messaging"]:
                sender_id = messaging_event["sender"]["id"]
                if "message" in messaging_event:
                    message_text = messaging_event["message"]["text"]
                    response_text = chat_with_gpt(message_text, sender_id)
                    send_message_messenger(sender_id, response_text)
    return "ok", 200

# 🔹 إدارة المحادثات والمبيعات

def chat_with_gpt(message, user_id):
    """ إدارة محادثة المستخدم والمبيعات """
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    prompt = f"انت مساعد بيع محترف، لازم تجاوب بالدارجة الجزائرية وتساعد العميل: {message}"
    payload = {"model": "gpt-4", "messages": [{"role": "system", "content": prompt}]}
    response = requests.post(url, headers=headers, json=payload)
    response_data = response.json()
    return response_data["choices"][0]["message"]["content"] if "choices" in response_data else "⛔ خطأ في الرد."
