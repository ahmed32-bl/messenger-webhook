import os
import requests
import json
from flask import Flask, request, jsonify
import openai
from dotenv import load_dotenv

# تحميل متغيرات البيئة من ملف .env (محليًا)
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
                    message_text = message_event["message"].get("text", "")

                    # 1) استرجاع آخر رسائل + الملخص
                    previous_messages = get_previous_messages(sender_id)
                    summary = get_summary(sender_id)

                    # 2) تمرير الرسالة إلى الدالة الرئيسية
                    bot_response = handle_user_message(sender_id, message_text, previous_messages, summary)

                    # 3) إرسال الرد للمستخدم
                    send_message(sender_id, bot_response)

                    # 4) حفظ الرسائل في Airtable
                    save_message(sender_id, message_text, "user")
                    save_message(sender_id, bot_response, "bot")

                    # 5) تحديث الملخص
                    update_summary(sender_id)
    return "OK", 200

########################################
# الدالة الرئيسية التي تستخدم برومبت شامل
########################################
def handle_user_message(user_id, message_text, previous_messages, summary):
    """
    1. نرسل رسالة من نوع system لـ GPT-4 تحتوي التعليمات (برومبت شامل).
    2. نطلب منه استخراج JSON بالمطلوب (intent, product_code, quantity...) 
    3. لو intent=buy_product نستدعي create_order وغيره
    4. لو intent=ask_product_info نستدعي get_product_by_code
    5. لو intent=out_of_scope نرد باعتذار
    6. إن لم نفهم يرد رد عام.
    """
    # نظُم التعليمات في برومبت شامل (System Prompt)
    system_prompt = f"""
أنت مساعد شخصي تلقائي (شات بوت) لمتجر إلكتروني يبيع "قمصان النور الإندونيسية" في الجزائر. 
تتكلم باللهجة الجزائرية شبه الرسمية، بدون إيموجي، وتبتعد عن التمييز بين الجنسين إلا لو واضح من كلام العميل.
دورك:
1. فهم سؤال العميل واستنباط نيته (هل يريد شراء، يسأل عن سعر، يسأل عن لون، إلخ).
2. إذا كان السؤال خارج نطاق الأقمصة والبيع، تعتذر بلباقة وتوضح أنك جاهز للمساعدة بالمنتجات.
3. تكلم بأسلوب أخوي مهذّب، واذكر "خويا" أو "أختي" حسب الحاجة لو كان واضحاً من الاسم، بدون مبالغة.
4. اقترح على العميل الألوان أو الموديلات الثانية إذا ما كان المنتج أو اللون المطلوب غير متوفر.
5. عند جمع البيانات الكافية للطلب، اطلب رقم الهاتف والعنوان لو لزم، ودون تمييز في الصيغة.
6. ردودك تكون مختصرة ومباشرة (سيمي-رسمية) وتحافظ على الود.

تنسيق الخرج: 
أعطني نتيجة على شكل JSON مثل:
{{
  "intent": "buy_product" أو "ask_product_info" أو "color_suggestion" أو "out_of_scope" أو "general",
  "product_code": "PROD001" (أو Null),
  "quantity": 1,
  "message_for_user": "النص المناسب للعميل"
}}

 إذا لا تستطيع استنباط أي intent، اجعل intent = "general" ثم أعد message_for_user.
 
سواء تكلم العميل عن أي شيء، أعد فقط JSON.

السياق السابق من المحادثة (آخر 5 رسائل):
{previous_messages}

ملخص سابق:
{summary}

رسالة العميل الحالية:
{message_text}
"""

    try:
        # استدعاء GPT-4 برسالة system + user فارغة
        # لأن النظام الأساسي سيكون في system_prompt
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "يرجى تحليل الرسالة وإعطاء JSON فقط"}
            ]
        )
        content = response["choices"][0]["message"].get("content", "").strip()

        # محاولة تحويل الـ content إلى JSON
        # إذا فشل التحويل، نرجع رد عام
        try:
            parsed = json.loads(content)
        except:
            # إذا ما قدرنا نفك JSON، يكون رد نصي عام
            return content

        # استخراج الحقول
        intent = parsed.get("intent", "general")
        product_code = parsed.get("product_code", None)
        quantity = parsed.get("quantity", 1)
        user_msg = parsed.get("message_for_user", "عذرًا، ما فهمتش قصدك.")

        # بناءً على النية نتصرف
        if intent == "buy_product" and product_code:
            # محاولة إنشاء طلب
            product_info = get_product_by_code(product_code)
            if product_info and product_info["stock"] >= quantity:
                # إنقاص المخزون
                new_stock = product_info["stock"] - quantity
                update_product_stock(product_info["record_id"], new_stock)
                # تسجيل الطلب
                create_order(user_id, product_code, quantity)
                return f"{user_msg}\n(تم تسجيل طلبك بنجاح: {product_info['product_name']} بعدد {quantity})"
            else:
                return f"{user_msg}\n(يظهر المنتج غير متوفر أو المخزون غير كافٍ.)"

        elif intent == "ask_product_info" and product_code:
            product_info = get_product_by_code(product_code)
            if product_info:
                return f"{user_msg}\n(لدينا {product_info['stock']} في المخزون بسعر {product_info['price']} دج.)"
            else:
                return f"{user_msg}\n(عذراً لا يوجد منتج بهذا الكود.)"

        elif intent == "color_suggestion":
            return user_msg  # مجرد رسالة من GPT-4

        elif intent == "out_of_scope":
            # سؤال خارج نطاق البيع
            return user_msg

        else:
            # general intent أو ما فهمناش
            return user_msg

    except Exception as e:
        print("GPT-4 Error:", e)
        return "عذرًا، حدث خطأ. حاول مرة أخرى لاحقًا."


########################################
# الدوال السابقة للمحادثة (الحفظ والتلخيص)
########################################
def get_previous_messages(user_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_MESSAGES}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        records = resp.json().get("records", [])
        msgs = []
        for r in records:
            flds = r.get("fields", {})
            if flds.get("user_id") == str(user_id):
                msgtxt = flds.get("message")
                if msgtxt:
                    msgs.append(msgtxt)
        # أعد آخر 5 رسائل فقط
        return "\n".join(msgs[-5:])
    return ""

def get_summary(user_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_SUMMARIES}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        recs = r.json().get("records", [])
        for rec in recs:
            flds = rec.get("fields", {})
            if flds.get("user_id") == str(user_id):
                return flds.get("summary", "")
    return ""

def update_summary(user_id):
    all_msgs = get_all_messages_list(user_id)
    if len(all_msgs) >= 10:
        summary_text = summarize_conversation(all_msgs)
        update_or_create_summary(user_id, summary_text)

def get_all_messages_list(user_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_MESSAGES}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    rr = requests.get(url, headers=headers)
    if rr.status_code == 200:
        recs = rr.json().get("records", [])
        msgs = []
        for r in recs:
            flds = r.get("fields", {})
            if flds.get("user_id") == str(user_id):
                msgtxt = flds.get("message")
                if msgtxt:
                    msgs.append(msgtxt)
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
    urlb = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_SUMMARIES}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    gg = requests.get(urlb, headers=headers)
    if gg.status_code == 200:
        recs = gg.json().get("records", [])
        existing_id = None
        for rc in recs:
            flds = rc.get("fields", {})
            if flds.get("user_id") == str(user_id):
                existing_id = rc["id"]
                break

        if existing_id:
            # تحديث
            patch_url = f"{urlb}/{existing_id}"
            patch_data = {
                "fields": {
                    "user_id": str(user_id),
                    "summary": summary_text
                }
            }
            requests.patch(patch_url, headers=headers, json=patch_data)
        else:
            # إنشاء سجل جديد
            data = {
                "fields": {
                    "user_id": str(user_id),
                    "summary": summary_text
                }
            }
            requests.post(urlb, headers=headers, json=data)


########################################
# إدارة المنتجات والطلبات
########################################
def get_product_by_code(product_code):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_PRODUCTS}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        recs = resp.json().get("records", [])
        for r in recs:
            flds = r.get("fields", {})
            if flds.get("product_code") == product_code:
                return {
                    "product_name": flds.get("product_name", ""),
                    "price": flds.get("price", 0),
                    "stock": flds.get("stock", 0),
                    "image_url": flds.get("image_url", ""),
                    "record_id": r["id"]
                }
    return None

def update_product_stock(record_id, new_stock):
    urlp = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_PRODUCTS}/{record_id}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    data = {"fields": {"stock": new_stock}}
    requests.patch(urlp, headers=headers, json=data)

def create_order(user_id, product_code, quantity, customer_name=None, phone_number=None, address=None):
    urlp = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_ORDERS}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
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

    resp = requests.post(urlp, headers=headers, json={"fields": fields_data})
    if resp.status_code in [200, 201]:
        return resp.json().get("fields", {})
    else:
        print("Error creating order:", resp.text)
        return None

def update_order_status(order_id, new_status):
    urlp = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_ORDERS}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    getresp = requests.get(urlp, headers=headers)
    if getresp.status_code == 200:
        recs = getresp.json().get("records", [])
        rec_id = None
        for rr in recs:
            flds = rr.get("fields", {})
            if flds.get("order_id") == order_id:
                rec_id = rr["id"]
                break
        if rec_id:
            patch_url = f"{urlp}/{rec_id}"
            patch_headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
            data = {"fields": {"status": new_status}}
            pr = requests.patch(patch_url, headers=patch_headers, json=data)
            if pr.status_code == 200:
                return True
            else:
                print("Error updating order status:", pr.text)
    return False


########################################
# حفظ الرسالة في Airtable (Messages)
########################################
def save_message(user_id, message_text, sender):
    urlm = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_MESSAGES}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    data = {
        "fields": {
            "user_id": str(user_id),
            "message": message_text,
            "sender": sender
        }
    }
    requests.post(urlm, headers=headers, json=data)


########################################
# إرسال رسالة نصية إلى ماسنجر
########################################
def send_message(recipient_id, message_text):
    urlm = "https://graph.facebook.com/v13.0/me/messages"
    headers = {"Content-Type": "application/json"}
    params = {"access_token": PAGE_ACCESS_TOKEN}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    requests.post(urlm, headers=headers, params=params, json=payload)

########################################
# نقطة البداية للتشغيل محليًا
########################################
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
