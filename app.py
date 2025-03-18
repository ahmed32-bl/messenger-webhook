import os
import requests
from flask import Flask, request, jsonify
import openai
from dotenv import load_dotenv

# إذا كنت تستخدم .env محليًا، سيُحمل متغيرات البيئة منه
load_dotenv()

app = Flask(__name__)

# =============================
# إعداد متغيرات البيئة
# =============================
AIRTABLE_API_KEY   = os.getenv("AIRTABLE_API_KEY")  # personal access token (أو PAT)
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

                    # جلب آخر 5 رسائل + الملخص السابق
                    previous_messages = get_previous_messages(sender_id)
                    summary = get_summary(sender_id)

                    # توليد رد من GPT-3.5-turbo أو ربطه بالمنطق الخاص بالشراء
                    response_text = process_message(
                        user_id=sender_id,
                        message_text=message_text,
                        previous_messages=previous_messages,
                        summary=summary
                    )

                    # إرسال الرد للمستخدم
                    send_message(sender_id, response_text)

                    # حفظ رسالة المستخدم
                    save_message(sender_id, message_text, "user")
                    # حفظ رد البوت
                    save_message(sender_id, response_text, "bot")

                    # تحديث الملخص (إذا وصل عدد الرسائل >= 10)
                    update_summary(sender_id)
    return "OK", 200

########################################
# 1) استرجاع آخر 5 رسائل (Messages)
########################################
def get_previous_messages(user_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_MESSAGES}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        records = response.json().get("records", [])
        messages_list = []
        for record in records:
            fields = record.get("fields", {})
            if fields.get("user_id") == str(user_id):
                msg_text = fields.get("message")
                if msg_text is not None:
                    messages_list.append(msg_text)
        return messages_list[-5:]  # آخر 5 رسائل فقط
    return []

########################################
# 2) استرجاع ملخص سابق من Summaries
########################################
def get_summary(user_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_SUMMARIES}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        records = response.json().get("records", [])
        for record in records:
            fields = record.get("fields", {})
            if fields.get("user_id") == str(user_id):
                return fields.get("summary", "")
    return ""

########################################
# 3) تحديث الملخص (إذا عدد الرسائل >= 10)
########################################
def update_summary(user_id):
    all_messages = get_all_messages(user_id)
    if len(all_messages) >= 10:
        summary_text = summarize_conversation(all_messages)
        update_or_create_summary(str(user_id), summary_text)

########################################
# استرجاع جميع الرسائل للمستخدم
########################################
def get_all_messages(user_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_MESSAGES}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        records = response.json().get("records", [])
        messages_list = []
        for record in records:
            fields = record.get("fields", {})
            if fields.get("user_id") == str(user_id):
                msg_text = fields.get("message")
                if msg_text is not None:
                    messages_list.append(msg_text)
        return messages_list
    return []

########################################
# إنشاء أو تحديث ملخص واحد لكل user_id
########################################
def update_or_create_summary(user_id, summary_text):
    url_base = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_SUMMARIES}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }

    get_resp = requests.get(url_base, headers=headers)
    if get_resp.status_code == 200:
        records = get_resp.json().get("records", [])
        record_id = None

        # ابحث عن سجل سابق يطابق user_id
        for record in records:
            fields = record.get("fields", {})
            if fields.get("user_id") == user_id:
                record_id = record["id"]
                break

        if record_id:
            # تحديث بسطر واحد (PATCH)
            patch_url = f"{url_base}/{record_id}"
            patch_data = {
                "fields": {
                    "user_id": user_id,
                    "summary": summary_text
                }
            }
            requests.patch(patch_url, headers=headers, json=patch_data)
        else:
            # إنشاء سجل جديد
            new_data = {
                "fields": {
                    "user_id": user_id,
                    "summary": summary_text
                }
            }
            requests.post(url_base, headers=headers, json=new_data)

########################################
# 4) تلخيص المحادثة
########################################
def summarize_conversation(messages):
    summary_prompt = (
        "لخص المحادثة التالية بإيجاز دون فقدان المعلومات المهمة:\n"
        + "\n".join(messages)
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", 
            messages=[{"role": "user", "content": summary_prompt}]
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("Summary Error:", e)
        return ""

########################################
# 5) الدوال الخاصة بإدارة المنتجات (Products)
########################################
def get_product_by_code(product_code):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_PRODUCTS}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        records = response.json().get("records", [])
        for record in records:
            fields = record.get("fields", {})
            if fields.get("product_code") == product_code:
                return {
                    "product_name": fields.get("product_name", ""),
                    "price": fields.get("price", 0),
                    "stock": fields.get("stock", 0),
                    "image_url": fields.get("image_url", ""),
                    "record_id": record["id"]
                }
    return None

def update_product_stock(record_id, new_stock):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_PRODUCTS}/{record_id}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {"fields": {"stock": new_stock}}
    requests.patch(url, headers=headers, json=data)

########################################
# 6) الدوال الخاصة بإدارة الطلبات (Orders)
########################################
def create_order(user_id, product_code, quantity, customer_name=None, phone_number=None, address=None):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_ORDERS}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    generated_order_id = f"ORD-{user_id}-{product_code}"

    data = {
        "fields": {
            "order_id": generated_order_id,
            "user_id": str(user_id),
            "product_code": product_code,
            "quantity": quantity,
            "status": "جديد"
        }
    }
    if customer_name:
        data["fields"]["customer_name"] = customer_name
    if phone_number:
        data["fields"]["phone_number"] = phone_number
    if address:
        data["fields"]["address"] = address

    resp = requests.post(url, headers=headers, json=data)
    if resp.status_code in [200, 201]:
        return resp.json().get("fields", {})
    else:
        print("Error creating order:", resp.text)
        return None

def update_order_status(order_id, new_status):
    # ابحث عن السجل الذي يحوي order_id في جدول Orders
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_ORDERS}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    get_resp = requests.get(url, headers=headers)
    if get_resp.status_code == 200:
        records = get_resp.json().get("records", [])
        record_id = None
        for record in records:
            fields = record.get("fields", {})
            if fields.get("order_id") == order_id:
                record_id = record["id"]
                break
        if record_id:
            patch_url = f"{url}/{record_id}"
            patch_headers = {
                "Authorization": f"Bearer {AIRTABLE_API_KEY}",
                "Content-Type": "application/json"
            }
            patch_data = {"fields": {"status": new_status}}
            patch_resp = requests.patch(patch_url, headers=patch_headers, json=patch_data)
            if patch_resp.status_code == 200:
                return True
            else:
                print("Error updating order status:", patch_resp.text)
    return False

########################################
# الدالة الرئيسية للردود باستخدام GPT + المنطق
########################################
def process_message(user_id, message_text, previous_messages, summary, model_name="gpt-3.5-turbo"):
    """
    حاليًا: 
    1. نكشف إذا كان المستخدم يريد شراء منتج (مثلاً ذكر كلمة "أريد شراء PROD001").
    2. إذا لم نكتشف شيئًا، نعتمد رد GPT-3.5-turbo على المحادثة السابقة.
    """
    try:
        # مثال: إذا اكتشفنا عبارة مثل: "أريد شراء PROD001 بكمية 2"
        if "أريد شراء" in message_text or "اطلب" in message_text:
            # ابحث عن product_code في النص (هذا مثال مبسط)
            # يمكنك تحسينه باستخدام RegEx
            tokens = message_text.split()
            product_code = None
            quantity = 1  # افتراضي

            for i, token in enumerate(tokens):
                if token.startswith("PROD") or token.startswith("QR"):
                    product_code = token
                # ابحث عن رقم للكمية
                if token.isdigit():
                    quantity = int(token)

            if product_code:
                # استعلام عن المنتج
                product_info = get_product_by_code(product_code)
                if product_info:
                    if product_info["stock"] >= quantity:
                        # إنشاء الطلب (هنا بشكل مبسط دون اسم العميل وهاتفه)
                        create_order(user_id, product_code, quantity)
                        # تقليل المخزون
                        new_stock = product_info["stock"] - quantity
                        update_product_stock(product_info["record_id"], new_stock)

                        return f"تم تسجيل طلبك لمنتج {product_info['product_name']} بعدد {quantity}، السعر {product_info['price']} دج. شكرا!"
                    else:
                        return f"للأسف المخزون غير كافٍ. المتوفر حالياً: {product_info['stock']} فقط."
                else:
                    return "عذراً، لم أجد المنتج المطلوب في القائمة."
            else:
                return "لم أفهم أي كود منتج. يرجى ذكر الكود مثل: PROD001"

        # إذا لم يكن طلب شراء، نعتمد GPT-3.5-turbo مع المحادثات السابقة + الملخص
        messages = [
            {"role": "system", "content": "أنت شات بوت جزائري تبيع أقمصة نور، رد باللهجة الجزائرية بدون إيموجي."}
        ]
        if summary:
            messages.append({"role": "system", "content": f"ملخص المحادثة السابقة: {summary}"})
        for msg in previous_messages:
            messages.append({"role": "user", "content": msg})
        messages.append({"role": "user", "content": message_text})

        response = openai.ChatCompletion.create(
            model=model_name,
            messages=messages
        )
        return response["choices"][0]["message"].get("content", "").strip()

    except Exception as e:
        print("OpenAI Error:", e)
        print("=================== ERROR STACK TRACE ===================")
        return "عذرًا، حدث خطأ. حاول مرة أخرى لاحقًا."

########################################
# حفظ الرسالة في Airtable (Messages)
########################################
def save_message(user_id, message_text, sender):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_MESSAGES}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "fields": {
            "user_id": str(user_id),
            "message": message_text,
            "sender": sender
        }
    }
    requests.post(url, headers=headers, json=data)

########################################
# إرسال رسالة نصية إلى ماسنجر
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
# نقطة البداية للتشغيل محليًا
########################################
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

