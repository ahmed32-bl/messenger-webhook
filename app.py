import os
import requests
import json
from flask import Flask, request, jsonify
import openai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# متغيرات البيئة
AIRTABLE_API_KEY   = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID   = os.getenv("AIRTABLE_BASE_ID")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
PAGE_ACCESS_TOKEN  = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN       = os.getenv("VERIFY_TOKEN")

# جداول Airtable
TABLE_MESSAGES     = "Messages"
TABLE_SUMMARIES    = "Summaries"
TABLE_PRODUCTS     = "Products"
TABLE_ORDERS       = "Orders"

openai.api_key = OPENAI_API_KEY

########################################
# Webhook Verification
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
                    user_message_text = message_event["message"].get("text", "")

                    # 1) جلب الرسائل السابقة والملخص
                    previous_msgs = get_previous_messages(sender_id)
                    summary = get_summary(sender_id)

                    # 2) جلب قائمة المنتجات الفعلية من Airtable
                    product_list = fetch_products()  # سيعيد لائحة من المنتجات

                    # 3) تعامل مع الرسالة
                    bot_response = handle_user_message(
                        user_id=sender_id,
                        user_text=user_message_text,
                        previous_messages=previous_msgs,
                        summary=summary,
                        product_list=product_list
                    )

                    # 4) إرسال الرد
                    send_text_message(sender_id, bot_response)

                    # 5) حفظ المحادثة
                    save_message(sender_id, user_message_text, "user")
                    save_message(sender_id, bot_response, "bot")

                    # 6) تحديث الملخص
                    update_summary(sender_id)

    return "OK", 200

########################################
# جلب كل المنتجات من Airtable
########################################
def fetch_products():
    """
    يعيد قائمة من القواميس:
    [
      {"product_code": "PROD001", "product_name": "قميص نور الأبيض", "price": 2500, "stock": 5, "image_url": "...", "color": "أبيض", "size": "M, L, XL"},
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
            fields = r.get("fields", {})
            product_list.append({
                "product_code": fields.get("product_code", ""),
                "product_name": fields.get("product_name", ""),
                "price": fields.get("price", 0),
                "stock": fields.get("stock", 0),
                "image_url": fields.get("image_url", ""),
                "color": fields.get("color", ""),
                "size": fields.get("size", "")
            })
    return product_list


########################################
# الدالة الرئيسية: استخدام برومبت شامل لـ GPT-4
########################################
def handle_user_message(user_id, user_text, previous_messages, summary, product_list):
    """
    نضع برومبت يحتوي على:
     - التعليمات الأساسية للهجة الجزائرية
     - قائمة المنتجات المتوفرة (حتى يلتزم GPT بها)
     - ملخص المحادثة السابقة
     - آخر 5 رسائل
     - رسالة العميل الحالية

    نطلب منه إخراج JSON يتضمن:
     intent, product_code, quantity, message_for_user, confirm_purchase

    ثم ننفذ الأمر ونجيب العميل.
    """
    # نحول قائمة المنتجات لJSON
    products_json = json.dumps(product_list, ensure_ascii=False)

    system_prompt = f"""
أنت مساعد شخصي تلقائي (شات بوت) لمتجر إلكتروني يبيع "قمصان النور الإندونيسية" في الجزائر.

- تتكلم باللهجة الجزائرية شبه الرسمية، دون إيموجي.
- هذه هي المنتجات المتوفرة فقط (لا تقترح شيئًا خارجها):
{products_json}

- إذا سأل العميل عن منتج، ابحث عن كوده (product_code) وطابقه مع القائمة أعلاه.
- لا تقدم منتج خارج هذه القائمة.
- إذا أراد الشراء، اطلب منه التأكيد قبل تسجيل الطلب (confirm_purchase=true).
- عند ذكر color أو size، تأكد أنها ضمن معلومات المنتج إن وجدت.
- إذا السؤال خارج نطاق الأقمصة أو البيع، اعتذر بلباقة.

السياق السابق (آخر 5 رسائل):
{previous_messages}

ملخص سابق:
{summary}

رسالة العميل الحالية:
{user_text}

أريد ردك في صيغة JSON حصراً، هكذا:
{{
  "intent": "...", 
  "product_code": "...", 
  "quantity": 1,
  "message_for_user": "نص مختصر للرد",
  "confirm_purchase": false
}}
حيث:
- intent يمكن أن يكون: "ask_product_info", "buy_product", "out_of_scope", "general"
- product_code يكون أحد الأكواد في القائمة، أو "" لو مافيه
- quantity رقم
- message_for_user رد موجز باللهجة الجزائرية.
- confirm_purchase = true إذا كنت جاهز لتأكيد الطلب
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            temperature=0.2,  # تقليل العشوائية
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "حلل الطلب وأعطني النتيجة في JSON فقط"}
            ]
        )
        content = response["choices"][0]["message"].get("content", "").strip()
        # محاولة parse JSON
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

        # تنفيذ المنطق بناء على intent
        if intent == "ask_product_info" and pcode:
            # ابحث عن المنتج في Airtable
            product_info = find_product_in_list(product_list, pcode)
            if product_info:
                # عرض المعلومات
                return f"{user_msg}\n(مخزون: {product_info['stock']}، سعر: {product_info['price']} دج)"
            else:
                return f"{user_msg}\n(عذراً ما لقينا هذا المنتج.)"

        elif intent == "buy_product" and pcode:
            # هل هذا تأكيد؟
            if confirm:
                # نتمم الطلب
                product_info = find_product_in_list(product_list, pcode)
                if product_info and product_info["stock"] >= qty:
                    # إنقاص المخزون
                    old_stock = product_info["stock"]
                    new_stock = old_stock - qty
                    # تحديثه في Airtable
                    p_rec_id = get_product_record_id(pcode)
                    if p_rec_id:
                        update_product_stock(p_rec_id, new_stock)
                        create_order(user_id, pcode, qty)
                        return f"{user_msg}\n(تم تسجيل طلبك: {product_info['product_name']} بعدد {qty} بنجاح.)"
                    else:
                        return f"{user_msg}\n(تعذر إتمام الطلب. لم أجد سجل المنتج.)"
                else:
                    return f"{user_msg}\n(المنتج غير متوفر أو المخزون لا يكفي.)"
            else:
                # لازال ناقص التأكيد
                return user_msg

        elif intent == "out_of_scope":
            return user_msg

        else:
            # general أو لا نعرف
            return user_msg

    except Exception as e:
        print("GPT-4 Error:", e)
        return "عذراً، صار خطأ تقني. أعد المحاولة لاحقاً."


########################################
# وظيفة بسيطة للبحث في القائمة
########################################
def find_product_in_list(product_list, product_code):
    for pr in product_list:
        if pr["product_code"] == product_code:
            return pr
    return None

########################################
# جلب record_id للمنتج من Airtable لتحديث المخزون
########################################
def get_product_record_id(product_code):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_PRODUCTS}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        recs = resp.json().get("records", [])
        for r in recs:
            flds = r.get("fields", {})
            if flds.get("product_code") == product_code:
                return r["id"]
    return None


########################################
# إرسال رسالة نصية لماسنجر
########################################
def send_text_message(recipient_id, message_text):
    url = "https://graph.facebook.com/v13.0/me/messages"
    headers = {"Content-Type": "application/json"}
    params = {"access_token": PAGE_ACCESS_TOKEN}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    requests.post(url, headers=headers, params=params, json=payload)


########################################
# حفظ المحادثات
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
# تحديث/إنشاء الملخص
########################################
def update_summary(user_id):
    msgs = get_all_messages_list(user_id)
    if len(msgs) >= 10:
        summ = summarize_conversation(msgs)
        update_or_create_summary(str(user_id), summ)


def get_previous_messages(user_id):
    # آخر 5 رسائل
    all_m = get_all_messages_list(user_id)
    return "\n".join(all_m[-5:])


def get_summary(user_id):
    urls = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_SUMMARIES}"
    h = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    rr = requests.get(urls, headers=h)
    if rr.status_code == 200:
        recs = rr.json().get("records", [])
        for r in recs:
            flds = r.get("fields", {})
            if flds.get("user_id") == str(user_id):
                return flds.get("summary", "")
    return ""


def get_all_messages_list(user_id):
    urll = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_MESSAGES}"
    hh = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    rr = requests.get(urll, headers=hh)
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
        print("Summary error:", e)
        return ""


def update_or_create_summary(user_id, summary_text):
    urlb = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_SUMMARIES}"
    heads = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    gg = requests.get(urlb, headers=heads)
    if gg.status_code == 200:
        recs = gg.json().get("records", [])
        exist_id = None
        for rc in recs:
            if rc.get("fields", {}).get("user_id") == user_id:
                exist_id = rc["id"]
                break
        if exist_id:
            # تحديث
            patch_url = f"{urlb}/{exist_id}"
            requests.patch(patch_url, headers=heads, json={
                "fields": {
                    "user_id": user_id,
                    "summary": summary_text
                }
            })
        else:
            # إنشاء
            requests.post(urlb, headers=heads, json={
                "fields": {
                    "user_id": user_id,
                    "summary": summary_text
                }
            })


########################################
# إدارة الطلبات
########################################
def create_order(user_id, product_code, quantity,
                 customer_name=None, phone_number=None, address=None):
    urlp = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_ORDERS}"
    hh = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    order_id = f"ORD-{user_id}-{product_code}"
    fields_data = {
        "order_id": order_id,
        "user_id": str(user_id),
        "product_code": product_code,
        "quantity": quantity,
        "status": "جديد"
    }
    if customer_name: fields_data["customer_name"] = customer_name
    if phone_number:  fields_data["phone_number"] = phone_number
    if address:       fields_data["address"] = address

    resp = requests.post(urlp, headers=hh, json={"fields": fields_data})
    if resp.status_code in [200, 201]:
        return resp.json().get("fields", {})
    else:
        print("Error creating order:", resp.text)
        return None


def update_order_status(order_id, new_status):
    urlp = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{TABLE_ORDERS}"
    hh = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    rget = requests.get(urlp, headers=hh)
    if rget.status_code == 200:
        recs = rget.json().get("records", [])
        rec_id = None
        for rr in recs:
            if rr.get("fields", {}).get("order_id") == order_id:
                rec_id = rr["id"]
                break
        if rec_id:
            patch_url = f"{urlp}/{rec_id}"
            data = {"fields": {"status": new_status}}
            pr = requests.patch(patch_url, headers={"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}, json=data)
            if pr.status_code == 200:
                return True
            else:
                print("Error updating status:", pr.text)
    return False


########################################
# تشغيل التطبيق
########################################
if __name__ == \"__main__\":
    app.run(host=\"0.0.0.0\", port=5000, debug=True)

