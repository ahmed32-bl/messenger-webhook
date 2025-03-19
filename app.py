import os
import requests
import logging
from flask import Flask, request, jsonify

# إعداد سجل التتبع
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# تحميل المتغيرات البيئية
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = "Liste_Couturiers"

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
                    
                    # معالجة بيانات الخياط
                    process_couturier(sender_id, user_message)
                    
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error(f"⚠️ خطأ أثناء معالجة الطلب: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

def process_couturier(sender_id, user_message):
    """ معالجة بيانات الخياط وإضافتها إلى Airtable """
    user_data = get_user_from_airtable(sender_id)
    
    if user_data:
        logging.info(f"🔎 الخياط موجود بالفعل في Airtable: {user_data}")
        send_message(sender_id, "📌 أنت مسجل بالفعل في قاعدة البيانات. إذا كنت تريد تعديل معلوماتك، تواصل معنا.")
    else:
        logging.info(f"🆕 خياط جديد - نبدأ عملية التسجيل")
        new_user = collect_user_data(sender_id, user_message)
        
        if new_user:
            add_user_to_airtable(new_user)
            send_message(sender_id, "✅ تم تسجيلك بنجاح! سنتواصل معك لاحقًا.")
        else:
            send_message(sender_id, "⚠️ لم يتم جمع جميع المعلومات المطلوبة. حاول مرة أخرى.")

def collect_user_data(sender_id, user_message):
    """ استخراج بيانات المستخدم من المحادثة (محاكي) """
    # ⚠️ في الخطوة القادمة سنستخدم DeepSeek لاستخراج البيانات تلقائيًا من المحادثة
    fake_data = {
        "Nom": "خياط تجريبي",
        "Genre": "رجل",
        "Ville": "وهران",
        "Experience": 5,
        "Type_Vetements": "سراويل وقمصان",
        "Materiel_Dispo": "آلة خياطة وأوفرلوك",
        "Disponibilite": "دوام كامل",
        "Telephone": "0555123456",
        "Contact_Proche": ""  # هذا الحقل يبقى فارغًا إذا كان الخياط رجلًا
    }

    # ✅ التأكد من أن الخياطات النساء يقدمن رقم قريب للتواصل
    if fake_data["Genre"] == "امرأة" and not fake_data["Contact_Proche"]:
        send_message(sender_id, "⚠️ بما أنك خياطة، يجب تقديم رقم قريب لك للتواصل. الرجاء إرسال الرقم.")
        return None

    return fake_data

def get_user_from_airtable(sender_id):
    """ التحقق مما إذا كان الخياط مسجلاً في Airtable """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        records = response.json().get("records", [])
        for record in records:
            if record["fields"].get("Telephone") == sender_id:
                return record["fields"]
    return None

def add_user_to_airtable(user_data):
    """ إضافة خياط جديد إلى Airtable """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "records": [
            {
                "fields": user_data
            }
        ]
    }
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 200:
        logging.info("✅ تم تسجيل الخياط في Airtable بنجاح!")
    else:
        logging.error(f"⚠️ خطأ في حفظ البيانات في Airtable: {response.text}")

def send_message(recipient_id, message_text):
    """ إرسال رد إلى المستخدم عبر Facebook Messenger """
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {PAGE_ACCESS_TOKEN}"}
    payload = {"recipient": {"id": recipient_id}, "message": {"text": message_text}}
    response = requests.post("https://graph.facebook.com/v18.0/me/messages", headers=headers, json=payload)

    if response.status_code != 200:
        logging.error(f"⚠️ فشل إرسال الرسالة: {response.text}")

if __name__ == "__main__":
    app.run(port=5000, debug=True)


