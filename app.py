import os
import requests
import json
from flask import Flask, request, jsonify
import openai
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

app = Flask(__name__)

# =============================
# متغيرات البيئة
# =============================
AIRTABLE_API_KEY  = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID  = os.getenv("AIRTABLE_BASE_ID")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN      = os.getenv("VERIFY_TOKEN")

# =============================
# أسماء الجداول في Airtable
# =============================
TABLE_MESSAGES  = "Messages"
TABLE_SUMMARIES = "Summaries"
TABLE_PRODUCTS  = "Products"
TABLE_ORDERS    = "Orders"

# تهيئة OpenAI
openai.api_key = OPENAI_API_KEY

########################################
# التحقق من Webhook فيسبوك
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

                    # 1) جلب آخر رسائل + ملخص
                    prev_msgs = get_previous_messages(sender_id)
                    conversation_summary = get_summary(sender_id)

                    # 2) جلب قائمة المنتجات
                    products_list = fetch_products()

                    # 3) تحليل الرسالة وإنتاج الرد
                    bot_reply = handle_user_message(
                        user_id=sender_id,
                        user_text=user_message,
                        previous_messages=prev_msgs,
                        summary=conversation_summary,
                        product_list=products_list
                    )

                    # 4) إرسال الرد
                    send_text_message(sender_id, bot_reply)

                    # 5) حفظ الرسائل
                    save_message(sender_id, user_message, "user")
                    save_message(sender_id, bot_reply, "bot")

                    # 6) تحديث الملخص
                    update_summary(sender_id)

    return "OK", 200


########################################
# 1) جلب قائمة المنتجات من Airtable
########################################
def fetch_products():
    """
    يعيد قائمة من القواميس:
    [
      {
        'product_code': 'PROD001',
        'product_name': 'قميص نور الأبيض',
        'price': 2500,
        'stock': 5,
        'image_url': '...',
        'color': 'أبيض',
        'size': 'M, L, XL'
      },
      ...
    ]
    """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_PRODUCTS}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    resp = requests.get(url, headers=headers)
    product_list = []
    if resp.status_code == 200:
        records = resp.json().get("records", [])
        for r in records:
            flds = r.get("fields", {})
            product_list.append({
                "product_code": flds.get("product_code", ""),
                "product_name": flds.get("product_name", ""),
                "price": flds.get("price", 0),
                "stock": flds.get("stock", 0),
                "image_url": flds.get("image_url", ""),
                "color": flds.get("color", ""),
                "size": flds.get("size", "")
            })
    return product_list


########################################
# 2) الدالة الرئيسية (برومبت شامل لـ GPT-4)
########################################
def handle_user_message(user_id, user_text, previous_messages, summary, product_list):
    """
    - نرسل لـ GPT-4 التعليمات الأساسية + قائمة المنتجات.
    - نطلب منه رد بشكل JSON: {intent, product_code, quantity, message_for_user, confirm_purchase}.
    - نتخذ القرار بناءً على الناتج.
    """
    products_json = json.dumps(product_list, ensure_ascii=False)

    system_prompt = f"""
أنت مساعد شخصي تلقائي (شات بوت) لمتجر إلكتروني يبيع قمصان النور الإندونيسية في الجزائر.
- تتحدث باللهجة الجزائرية شبه الرسمية دون إيموجي.
- هذه قائمة المنتجات المتوفرة فقط (لا تقترح أي شيء خارجها):
{products_json}

- إذا أراد العميل شراء منتج، اطلب منه تأكيد الشراء (confirm_purchase = true) قبل إتمام الطلب.
- إذا كان خارج نطاق البيع، اعتذر بلباقة.
- رجاءً أعد الرد بصيغة JSON حصراً:
{{
  \"intent\": \"...\",
  \"product_code\": \"...\",
  \"quantity\": 1,
  \"message_for_user\": \"...\", 
  \"confirm_purchase\": false
}}

سياق المحادثة السابقة (آخر 5 رسائل):
{previous_messages}

ملخص سابق:
{summary}

رسالة العميل الحالية:
{user_text}
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            temperature=0.2,  # تقليل العشوائية
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "حلل الرسالة وأعطني JSON فقط."}
            ]
        )
        content = response["choices"][0]["message"].get("content", "").strip()

        # محاولة تفكيك JSON
        try:
            parsed = json.loads(content)
        except:
            # لو فشل، نرجع المحتوى كما هو
            return content

        # نقرأ القيم
        intent = parsed.get("intent", "general")
        pcode = parsed.get("product_code", "")
        qty = parsed.get("quantity", 1)
        confirm = parsed.get("confirm_purchase", False)
        user_msg = parsed.get("message_for_user", "ما فهمتش قصدك.")

        # لو nية: معلومات منتج
        if intent == "ask_product_info" and pcode:
            product_info = find_in_list(product_list, pcode)
            if product_info:
                return f"{user_msg}\n(مخزون: {product_info['stock']}, سعر: {product_info['price']} دج)"
            else:
                return f"{user_msg}\n(ما لقيتش المنتج المطلوب.)"

        # لو nية: شراء منتج
        elif intent == "buy_product" and pcode:
            if confirm:
                # تأكيد الشراء، نسجل الطلب وننقص المخزون
                product_info = find_in_list(product_list, pcode)
                if product_info and product_info["stock"] >= qty:
                    # تحديث المخزون في Airtable
                    record_id = get_product_record_id(pcode)
                    if record_id:
                        new_stock = product_info["stock"] - qty
                        update_product_stock(record_id, new_stock)
                        create_order(user_id, pcode, qty)
                        return f"{user_msg}\n(تم تسجيل طلبك لمنتج {product_info['product_name']} بعدد {qty}.)"
                    else:
                        return f"{user_msg}\n(تعذر إتمام الطلب، لم أجد سجل المنتج.)"
                else:
                    return f"{user_msg}\n(المخزون ما يكفي أو المنتج غير موجود.)"
            else:
                # لسه مافي تأكيد
                return user_msg

        # لو خارج النطاق
        elif intent == "out_of_scope":
            return user_msg

        else:
            # general intent أو ما فهمناش
            return user_msg

    except Exception as e:
        print("GPT-4 Error:", e)
        return "عذرًا، صار خطأ تقني. أعد المحاولة لاحقاً."


########################################
# بحث عن المنتج في القائمة
########################################
def find_in_list(product_list, product_code):
    for prod in product_list:
        if prod["product_code"] == product_code:
            return prod
    return None


########################################
# جلب record_id للمنتج من Airtable
########################################
def get_product_record_id(product_code):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_PRODUCTS}"
    hh = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    resp = requests.get(url, headers=hh)
    if resp.status_code == 200:
        recs = resp.json().get("records", [])
        for r in recs:
            fields = r.get("fields", {})
            if fields.get("product_code") == product_code:
                return r["id"]
    return None

########################################
# إرسال رسالة نصية لماسنجر
########################################
def send_text_message(recipient_id, message_text):
    fb_url = "https://graph.facebook.com/v13.0/me/messages"
    headers = {"Content-Type": "application/json"}
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    requests.post(fb_url, headers=headers, params=params, json=data)


########################################
# حفظ الرسالة في Airtable (Messages)
########################################
def save_message(user_id, message_text, sender):
    url_msg = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_MESSAGES}"
    hh = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    data = {
        "fields": {
            "user_id": str(user_id),
            "message": message_text,
            "sender": sender
        }
    }
    requests.post(url_msg, headers=hh, json=data)

########################################
# تحديث الملخص عند وصول 10 رسائل
########################################
def update_summary(user_id):
    msgs_list = get_all_messages(user_id)
    if len(msgs_list) >= 10:
        summ = summarize_conversation(msgs_list)
        update_or_create_summary(str(user_id), summ)

def get_previous_messages(user_id):
    all_msgs = get_all_messages(user_id)
    return "\n".join(all_msgs[-5:])

def get_summary(user_id):
    url_summ = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_SUMMARIES}"
    hh = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    r = requests.get(url_summ, headers=hh)
    if r.status_code == 200:
        recs = r.json().get("records", [])
        for rec in recs:
            flds = rec.get("fields", {})
            if flds.get("user_id") == str(user_id):
                return flds.get("summary", "")
    return ""

def get_all_messages(user_id):
    url_msg = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_MESSAGES}"
    hh = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    rr = requests.get(url_msg, headers=hh)
    if rr.status_code == 200:
        recs = rr.json().get("records", [])
        msgs = []
        for rc in recs:
            flds = rc.get("fields", {})
            if flds.get("user_id") == str(user_id):
                msgs.append(flds.get("message", ""))
        return msgs
    return []

def summarize_conversation(messages_list):
    joined = "\n".join(messages_list)
    prompt = f"لخص المحادثة التالية بإيجاز دون فقدان المعلومات المهمة:\n{joined}"
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        return resp["choices"][0]["message"].get("content", "").strip()
    except Exception as e:
        print("Summary Error:", e)
        return ""

def update_or_create_summary(user_id, summary_text):
    url_summ = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_SUMMARIES}"
    hh = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    resp = requests.get(url_summ, headers=hh)
    if resp.status_code == 200:
        recs = resp.json().get("records", [])
        existing_id = None
        for rr in recs:
            if rr.get("fields", {}).get("user_id") == user_id:
                existing_id = rr["id"]
                break
        if existing_id:
            # Patch
            patch_url = f"{url_summ}/{existing_id}"
            requests.patch(patch_url, headers=hh, json={
                "fields": {
                    "summary": summary_text
                }
            })
        else:
            # Create
            requests.post(url_summ, headers=hh, json={
                "fields": {
                    "user_id": user_id,
                    "summary": summary_text
                }
            })


########################################
# إدارة الطلبات
########################################
def create_order(user_id, product_code, quantity, customer_name=None, phone_number=None, address=None):
    url_o = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_ORDERS}"
    hh = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    order_id = f"ORD-{user_id}-{product_code}"
    fields_data = {
        "order_id": order_id,
        "user_id": str(user_id),
        "product_code": product_code,
        "quantity": quantity,
        "status": "جديد"
    }
    if customer_name:
        fields_data["customer_name"] = customer_name
    if phone_number:
        fields_data["phone_number"] = phone_number
    if address:
        fields_data["address"] = address

    rr = requests.post(url_o, headers=hh, json={"fields": fields_data})
    if rr.status_code in [200, 201]:
        return rr.json().get("fields", {})
    else:
        print("Error creating order:", rr.text)
        return None

def update_product_stock(record_id, new_stock):
    url_p = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_PRODUCTS}/{record_id}"
    hh = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    data = {"fields": {"stock": new_stock}}
    requests.patch(url_p, headers=hh, json=data)

def update_order_status(order_id, new_status):
    url_o = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_ORDERS}"
    hh = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    rget = requests.get(url_o, headers=hh)
    if rget.status_code == 200:
        recs = rget.json().get("records", [])
        rec_id = None
        for rc in recs:
            if rc.get("fields", {}).get("order_id") == order_id:
                rec_id = rc["id"]
                break
        if rec_id:
            patch_url = f"{url_o}/{rec_id}"
            data = {"fields": {"status": new_status}}
            pr = requests.patch(patch_url, headers={"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}, json=data)
            if pr.status_code == 200:
                return True
            else:
                print("Error updating order status:", pr.text)
    return False


########################################
# نقطة البداية
########################################
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
