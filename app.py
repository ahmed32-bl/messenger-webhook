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
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# إعداد أسماء الجداول
CONVERSATIONS_TABLE = "Conversations"
WORKERS_TABLE = "Liste_Couturiers"

# إعداد تطبيق Flask
app = Flask(__name__)

def get_deepseek_response(chat_history, user_message):
    """ إرسال رسالة إلى DeepSeek والحصول على الرد """
    try:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        data = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "راك مساعد آلي تخدم مع الورشة، مهمتك تجمع المعلومات من الخياطين وتجاوبهم على أسئلتهم على الخدمة. "
                        "تهدر بالدارجة الجزائرية بأسلوب محترم وأخوي، تبقى مركز على جمع المعلومات وما تخرجش على الموضوع. "
                        "إذا سألك العامل على حاجة ما عندهاش علاقة بالخدمة، قول له بلطافة بلي راك هنا غير باش تهدر على الخدمة. "
                        "ابدأ بالسؤال عن الجنس، وإذا كانت المتحدثة امرأة، سجل اسم الفيسبوك بدون سؤالها عن اسمها. "
                        "اطرح الأسئلة واحدة بواحدة وتأكد أن العامل يجاوب على كل سؤال قبل ما تمر للسؤال اللي بعده. "
                        "لا تطلب رقم قريب المرأة حتى النهاية، واشرح لها بلطف السبب قبل ما تطلبه."
                    ),
                },
                {"role": "user", "content": chat_history},
                {"role": "user", "content": user_message}
            ]
        }
        response = requests.post(url, json=data, headers=headers)
        return response.json().get("choices", [{}])[0].get("message", {}).get("content", "معذرة، ما قدرتش نفهمك، عاود جرب بصيغة أخرى.")
    except Exception as e:
        logging.error(f"⚠️ خطأ عند الاتصال بـ DeepSeek: {str(e)}")
        return "عذراً، ما قدرت نجاوبك." 

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
                    process_message(sender_id, user_message)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error(f"⚠️ خطأ أثناء معالجة الطلب: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

def process_message(sender_id, user_message):
    """ معالجة الرسالة الجديدة باستخدام DeepSeek """
    conversation = get_conversation_history(sender_id)
    chat_history = ""
    if conversation and "fields" in conversation:
        chat_history = conversation["fields"].get("conversation_history", "")
    
    bot_response = get_deepseek_response(chat_history, user_message)
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



