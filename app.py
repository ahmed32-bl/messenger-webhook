from flask import Flask, request, jsonify
import requests
import logging
import os

app = Flask(__name__)

# إعداد سجل التتبع
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# جلب مفاتيح API من المتغيرات البيئية
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

deepseek_url = "https://api.deepseek.com/v1/chat/completions"  # تأكد من رابط API الصحيح

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        sender_id = data['entry'][0]['messaging'][0]['sender']['id']
        message_text = data['entry'][0]['messaging'][0]['message']['text']

        logging.info(f"📩 استقبال رسالة من {sender_id}: {message_text}")
        
        # إرسال الطلب إلى DeepSeek
        payload = {
            "model": "deepseek-chat",  # ✅ حدد نوع النموذج هنا
            "messages": [
                {"role": "system", "content": "أنت مساعد ذكي يرد بالدارجة الجزائرية."},
                {"role": "user", "content": message_text}
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }

        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.post(deepseek_url, json=payload, headers=headers)
        response_data = response.json()

        bot_response = response_data.get("response", "عذرًا، ما قدرت نجاوبك.")

        return jsonify({"status": "success", "response": bot_response})
    except Exception as e:
        logging.error(f"⚠️ خطأ أثناء معالجة الطلب: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(port=5000, debug=True)
