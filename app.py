import os
import requests
from flask import Flask, request, jsonify
import openai
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

app = Flask(__name__)

# =============================
# إعداد متغيرات البيئة
# =============================
AIRTABLE_API_KEY   = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID   = os.getenv("AIRTABLE_BASE_ID")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
PAGE_ACCESS_TOKEN  = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN       = os.getenv("VERIFY_TOKEN")

# =============================
# أسماء الجداول في Airtable
# =============================
TABLE_MESSAGES     = "Messages"
TABLE_SUMMARIES    = "Summaries"
TABLE_PRODUCTS     = "Products"
TABLE_ORDERS       = "Orders"

# =============================
# إعداد مفتاح OpenAI
# =============================
openai.api_key = OPENAI_API_KEY

########################################
# نقطة النهاية للتحقق من Webhook في فيسبوك
########################################
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    token_sent = request.args.get("hub.verify_token")
    if token_sent == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Unauthorized", 403

########################################
# استقبال الرسائل من ماسنجر
########################################
@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for message_event in entry.get("messaging", []):
                sender_id = message_event.get("sender", {}).get("id")
                if message_event.get("message"):
                    message_text = message_event["message"].get("text")
                    
                    # تحليل السؤال باستخدام GPT-4
                    intent = analyze_intent(message_text)
                    
                    if intent == "order":
                        response_text = handle_order(sender_id, message_text)
                    elif intent == "product_info":
                        response_text = get_product_info(message_text)
                    elif intent == "color_suggestion":
                        response_text = suggest_colors()
                    else:
                        response_text = process_message(sender_id, message_text)
                    
                    # إرسال الرد
                    send_message(sender_id, response_text)
                    save_message(sender_id, message_text, "user")
                    save_message(sender_id, response_text, "bot")
    return "OK", 200

########################################
# تحليل السؤال باستخدام GPT-4
########################################
def analyze_intent(message_text):
    prompt = f"""
    حدد نوع السؤال بناءً على المحتوى التالي: {message_text}
    الأنواع المحتملة:
    - "order" إذا كان المستخدم يريد شراء منتج.
    - "product_info" إذا كان المستخدم يسأل عن منتج.
    - "color_suggestion" إذا كان يريد اقتراح ألوان أو موديلات أخرى.
    - "general" لأي سؤال عام.
    """
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "system", "content": prompt}]
    )
    return response["choices"][0]["message"].get("content", "general").strip()

########################################
# التعامل مع الطلبات
########################################
def handle_order(user_id, message_text):
    tokens = message_text.split()
    product_code, quantity = None, 1
    for i, token in enumerate(tokens):
        if token.startswith("PROD"):
            product_code = token
        if token.isdigit():
            quantity = int(token)
    if product_code:
        product_info = get_product_by_code(product_code)
        if product_info and product_info["stock"] >= quantity:
            create_order(user_id, product_code, quantity)
            update_product_stock(product_info["record_id"], product_info["stock"] - quantity)
            return f"تم تسجيل طلبك لمنتج {product_info['product_name']} بعدد {quantity} بسعر {product_info['price']} دج. شكرا!"
        else:
            return "للأسف المخزون غير كافٍ أو المنتج غير موجود."
    return "يرجى ذكر كود المنتج مثل: PROD001"

########################################
# جلب معلومات المنتج
########################################
def get_product_info(message_text):
    product_code = message_text.split()[-1]
    product_info = get_product_by_code(product_code)
    if product_info:
        return f"{product_info['product_name']} متوفر بسعر {product_info['price']} دج، لدينا {product_info['stock']} قطعة متاحة."
    return "عذرًا، لم أجد المنتج المطلوب."

########################################
# اقتراح ألوان أخرى
########################################
def suggest_colors():
    return "لدينا مجموعة من الألوان المتاحة! يرجى تحديد اللون المطلوب أو الاطلاع على القائمة الكاملة."

########################################
# إرسال الردود عبر فيسبوك ماسنجر
########################################
def send_message(recipient_id, message_text):
    url = "https://graph.facebook.com/v13.0/me/messages"
    headers = {"Content-Type": "application/json"}
    params = {"access_token": PAGE_ACCESS_TOKEN}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    requests.post(url, headers=headers, params=params, json=payload)

########################################
# حفظ الرسائل في Airtable
########################################
def save_message(user_id, message_text, sender):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_MESSAGES}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    data = {"fields": {"user_id": str(user_id), "message": message_text, "sender": sender}}
    requests.post(url, headers=headers, json=data)

########################################
# تشغيل التطبيق
########################################
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)


