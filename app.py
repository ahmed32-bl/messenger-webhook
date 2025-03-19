import os
import requests
import json
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# تحميل المتغيرات من .env
load_dotenv()

app = Flask(__name__)

# =============================
# إعداد متغيرات البيئة
# =============================
AIRTABLE_API_KEY   = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID   = os.getenv("AIRTABLE_BASE_ID")
DEEPSEEK_API_KEY   = os.getenv("DEEPSEEK_API_KEY")
PAGE_ACCESS_TOKEN  = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN       = os.getenv("VERIFY_TOKEN")

# =============================
# أسماء الجداول في Airtable
# =============================
TABLE_MESSAGES  = "Messages"
TABLE_SUMMARIES = "Summaries"
TABLE_PRODUCTS  = "Products"
TABLE_ORDERS    = "Orders"

# =============================
# DeepSeek API
# =============================
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

########################################
# التحقق من Webhook في فيسبوك
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
                sender_id = message_event.get("sender", {}).get("id", "")
                if message_event.get("message"):
                    user_message = message_event["message"].get("text", "")

                    # جلب بيانات المحادثة السابقة
                    prev_msgs = get_previous_messages(sender_id)
                    conversation_summary = get_summary(sender_id)
                    products_list = fetch_products()

                    # تحليل الرسالة باستخدام DeepSeek
                    bot_reply, image_url = handle_user_message(
                        user_id=sender_id,
                        user_text=user_message,
                        previous_messages=prev_msgs,
                        summary=conversation_summary,
                        product_list=products_list
                    )

                    # إرسال الرد للمستخدم
                    send_message(sender_id, bot_reply, image_url)

                    # حفظ المحادثة
                    save_message(sender_id, user_message, "user")
                    save_message(sender_id, bot_reply, "bot")

                    # تحديث الملخص
                    update_summary(sender_id)

    return "OK", 200

########################################
# جلب قائمة المنتجات من Airtable
########################################
def fetch_products():
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_PRODUCTS}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    resp = requests.get(url, headers=headers)

    products = []
    if resp.status_code == 200:
        records = resp.json().get("records", [])
        for record in records:
            fields = record.get("fields", {})
            products.append({
                "product_code": fields.get("product_code", ""),
                "product_name": fields.get("name", ""),
                "price": fields.get("price", 0),
                "stock": fields.get("stock", 0),
                "image_url": fields.get("image_url", [{}])[0].get("url", "") if "image_url" in fields else "",
                "color": fields.get("color", ""),
                "size": fields.get("size", ""),
                "description": fields.get("description", "")
            })
    return products

########################################
# تحليل الرسائل باستخدام DeepSeek
########################################
def handle_user_message(user_id, user_text, previous_messages, summary, product_list):
    products_json = json.dumps(product_list, ensure_ascii=False)

    system_prompt = f"""
    أنت مساعد آلي لمتجر أقمصة النور في الجزائر، تتحدث باللهجة الجزائرية الشبه رسمية دون إيموجي.
    المنتجات المتاحة فقط هي:
    {products_json}

    التعليمات:
    - إذا لم تفهم المستخدم، اطلب منه إعادة الصياغة.
    - إذا سأل عن منتج، قدم له التفاصيل (السعر، الألوان، المقاسات، الصورة، المخزون).
    - إذا أراد الشراء، اطلب منه تأكيد الطلب قبل تسجيله.

    الرد يكون في JSON:
    {{
      "intent": "general" / "ask_product_info" / "buy_product" / "need_clarification",
      "product_code": "..." أو "" إذا لم يكن متعلقًا بمنتج,
      "quantity": رقم الكمية المطلوبة (إذا لم يحدد، ضع 1),
      "confirm_purchase": true إذا كان جاهزًا للشراء، false إذا يحتاج تأكيد,
      "message_for_user": "..."
    }}

    سياق المحادثة:
    {previous_messages}

    ملخص المحادثة:
    {summary}

    رسالة المستخدم:
    {user_text}
    """

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ]
    }

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload)
        response_data = response.json()

        if "choices" in response_data:
            bot_reply = response_data["choices"][0]["message"]["content"].strip()
            parsed = json.loads(bot_reply)

            intent = parsed.get("intent", "general")
            product_code = parsed.get("product_code", "")
            quantity = parsed.get("quantity", 1)
            confirm = parsed.get("confirm_purchase", False)
            user_msg = parsed.get("message_for_user", "ما فهمتش قصدك.")

            if intent == "need_clarification":
                return user_msg, None

            if intent == "ask_product_info" and product_code:
                product_info = next((p for p in product_list if p["product_code"] == product_code), None)
                if product_info:
                    return f"{user_msg}\n🛒 {product_info['product_name']} - {product_info['price']} دج\n🎨 اللون: {product_info['color']}\n📏 المقاسات: {product_info['size']}\n📦 المخزون: {product_info['stock']} قطعة", product_info["image_url"]
                else:
                    return "عذراً، هذا المنتج غير متاح.", None

            if intent == "buy_product" and product_code:
                if confirm:
                    create_order(user_id, product_code, quantity)
                    return f"✅ تم تسجيل طلبك بنجاح!", None
                else:
                    return f"{user_msg}\nهل ترغب في تأكيد الطلب؟", None

            return user_msg, None
        else:
            return "عذراً، لم أتمكن من معالجة طلبك.", None

    except Exception as e:
        print("DeepSeek API Error:", e)
        return "عذراً، صار خطأ تقني.", None

########################################
# إرسال الرسائل والصور لماسنجر
########################################
def send_message(recipient_id, message_text, image_url=None):
    fb_url = "https://graph.facebook.com/v13.0/me/messages"
    headers = {"Content-Type": "application/json"}
    params = {"access_token": PAGE_ACCESS_TOKEN}

    if image_url:
        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "image",
                    "payload": {"url": image_url, "is_reusable": True}
                }
            }
        }
        requests.post(fb_url, headers=headers, params=params, json=payload)

    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    requests.post(fb_url, headers=headers, params=params, json=payload)

########################################
# تشغيل التطبيق
########################################
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

