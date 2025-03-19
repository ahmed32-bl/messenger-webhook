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

# إعداد أسماء الجداول
CONVERSATIONS_TABLE = "Conversations"
WORKERS_TABLE = "Liste_Couturiers"

# إعداد تطبيق Flask
app = Flask(__name__)

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
                    
                    # معالجة المحادثة وتحديث البيانات
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
    """ حفظ المحادثة في Airtable - يسجل جميع العمال الذين راسلوا البوت """
    conversation = get_conversation_history(sender_id)
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{CONVERSATIONS_TABLE}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }

    if conversation:
        record_id = conversation["id"]
        old_history = conversation["fields"].get("Messages_History", "")
        new_history = old_history + f"\n👤 المستخدم: {user_message}\n🤖 البوت: {bot_response}"
        
        data = {"fields": {
            "Messages_History": new_history,
            "Dernier_Message": user_message,
            "Date_Dernier_Contact": str(datetime.now().date())
        }}
        url_update = f"{url}/{record_id}"
        requests.patch(url_update, json=data, headers=headers)
    else:
        data = {"records": [{
            "fields": {
                "Messenger_ID": sender_id,
                "Messages_History": f"👤 المستخدم: {user_message}\n🤖 البوت: {bot_response}",
                "Dernier_Message": user_message,
                "Date_Dernier_Contact": str(datetime.now().date())
            }
        }]}
        requests.post(url, json=data, headers=headers)

def get_couturier_id_from_conversations(sender_id):
    """ البحث عن ID_Couturier في Conversations """
    conversation = get_conversation_history(sender_id)
    if conversation:
        return conversation["fields"].get("ID_Couturier")
    return None

def check_worker_eligibility(conversation):
    """ التحقق مما إذا كان العامل استوفى جميع الشروط """
    required_fields = ["Nom", "Genre", "Ville", "Experience", "Type_Vetements",
                       "Materiel_Dispo", "Disponibilite", "Telephone"]
    
    for field in required_fields:
        if field not in conversation["fields"] or not conversation["fields"][field]:
            return False  # لا يزال هناك بيانات ناقصة

    # إذا كانت المتقدمة امرأة، يجب أن يكون هناك رقم قريب
    if conversation["fields"]["Genre"] == "امرأة" and not conversation["fields"].get("Contact_Proche"):
        return False

    return True  # جميع الشروط مستوفاة

def move_to_workers_list(sender_id):
    """ نقل العامل إلى Liste_Couturiers بنفس ID_Couturier مع ربطه بجدول Conversations """
    conversation = get_conversation_history(sender_id)
    couturier_id = get_couturier_id_from_conversations(sender_id)

    if conversation and couturier_id and check_worker_eligibility(conversation):
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{WORKERS_TABLE}"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}",
            "Content-Type": "application/json"
        }
        
        worker_data = {
            "fields": {
                "ID_Couturier": couturier_id,
                "Conversation_ID": [couturier_id],  # ربط السجل بالمحادثات
                "Nom": conversation["fields"]["Nom"],
                "Genre": conversation["fields"]["Genre"],
                "Ville": conversation["fields"]["Ville"],
                "Experience": conversation["fields"]["Experience"],
                "Type_Vetements": conversation["fields"]["Type_Vetements"],
                "Materiel_Dispo": conversation["fields"]["Materiel_Dispo"],
                "Disponibilite": conversation["fields"]["Disponibilite"],
                "Telephone": conversation["fields"]["Telephone"],
                "Contact_Proche": conversation["fields"].get("Contact_Proche", ""),
                "Statut": "مقبول",
                "Date_Inscription": str(datetime.now().date())
            }
        }

        response = requests.post(url, json={"records": [worker_data]}, headers=headers)
        if response.status_code == 200:
            logging.info(f"✅ تم نقل العامل إلى Liste_Couturiers بنفس ID: {couturier_id}")
        else:
            logging.error(f"⚠️ خطأ في نقل العامل: {response.text}")

def process_message(sender_id, user_message):
    """ معالجة الرسالة الجديدة """
    conversation = get_conversation_history(sender_id)

    if conversation:
        chat_history = conversation["fields"].get("Messages_History", "")
    else:
        chat_history = ""

    bot_response = "تم تسجيل رسالتك، سيتم التواصل معك قريبًا!"  # سنضيف الذكاء لاحقًا
    send_message(sender_id, bot_response)
    save_conversation(sender_id, user_message, bot_response)

    move_to_workers_list(sender_id)

def send_message(recipient_id, message_text):
    """ إرسال رد إلى المستخدم عبر Facebook Messenger """
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {PAGE_ACCESS_TOKEN}"}
    payload = {"recipient": {"id": recipient_id}, "message": {"text": message_text}}
    requests.post("https://graph.facebook.com/v18.0/me/messages", headers=headers, json=payload)

if __name__ == "__main__":
    app.run(port=5000, debug=True)


