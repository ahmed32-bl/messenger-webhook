import logging
from flask import Flask, request, jsonify
from orders import handle_order, get_order_status
from stock import handle_stock_request
from marketing import handle_marketing
from customer_service import handle_customer_service
import utils
from deepseek import process_message  # استبدال GPT بـ DeepSeek

# إعداد نظام تسجيل العمليات
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        sender_id = data['entry'][0]['messaging'][0]['sender']['id']
        message_text = data['entry'][0]['messaging'][0]['message']['text']

        logging.info(f"استقبال رسالة من {sender_id}: {message_text}")

        # تحليــل محتوى الرسالة وتحديد الفئة المناسبة للرد
        if "طلب" in message_text or "commande" in message_text:
            if "حالة" in message_text or "statut" in message_text:
                response = get_order_status(sender_id, message_text)
            else:
                response = handle_order(sender_id, message_text)
        elif "المخزون" in message_text or "stock" in message_text:
            response = handle_stock_request(sender_id, message_text)
        elif "عرض" in message_text or "promo" in message_text:
            response = handle_marketing(sender_id, message_text)
        else:
            response = handle_customer_service(sender_id, message_text)

        # إرسال الرد إلى المستخدم عبر DeepSeek
        processed_response = process_message(response)
        utils.send_message(sender_id, processed_response)

        logging.info(f"تم إرسال الرد إلى {sender_id}: {processed_response}")
        return jsonify({"status": "success"})
    except Exception as e:
        logging.error(f"خطأ أثناء معالجة الطلب: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(port=5000, debug=True)

# orders.py - إدارة الطلبات

def handle_order(sender_id, message_text):
    """معالجة طلبات العملاء وحفظها في Airtable"""
    order_details = utils.extract_order_details(message_text)
    utils.save_to_airtable("Orders", order_details)
    return "تم تسجيل طلبك بنجاح!"

def get_order_status(sender_id, message_text):
    """استرجاع حالة الطلب من Airtable"""
    order_status = utils.fetch_from_airtable("Orders", sender_id)
    return f"حالة طلبك: {order_status}" if order_status else "لا يوجد طلب مسجل برقمك."

# stock.py - إدارة المخزون

def handle_stock_request(sender_id, message_text):
    """التحقق من توفر المخزون"""
    stock_status = utils.check_stock_availability(message_text)
    return stock_status

# marketing.py - إدارة العروض التسويقية

def handle_marketing(sender_id, message_text):
    """إرسال العروض الترويجية وفقًا لنشاط العميل"""
    promo_message = utils.get_promo_message(sender_id)
    return promo_message

# customer_service.py - خدمة العملاء

def handle_customer_service(sender_id, message_text):
    """معالجة استفسارات العملاء"""
    response = utils.get_customer_response(sender_id, message_text)
    return response

# utils.py - وظائف المساعدة
import airtable

def send_message(sender_id, message):
    """إرسال رسالة عبر Messenger API"""
    print(f"إرسال رسالة إلى {sender_id}: {message}")

def extract_order_details(message_text):
    """تحليل تفاصيل الطلب من نص الرسالة"""
    return {"order_text": message_text}

def save_to_airtable(table_name, data):
    """حفظ البيانات في Airtable"""
    print(f"حفظ البيانات في {table_name}: {data}")

def fetch_from_airtable(table_name, sender_id):
    """استرجاع بيانات الطلب من Airtable بناءً على معرف المرسل"""
    return "تم شحن الطلب"  # مثال تجريبي، يلزم ربط Airtable الفعلي

def check_stock_availability(message_text):
    """التحقق من توفر المنتج في المخزون"""
    return "المخزون متاح لهذا المنتج."

def get_promo_message(sender_id):
    """استرداد العروض الترويجية المناسبة"""
    return "لدينا عرض خاص لك اليوم!"

def get_customer_response(sender_id, message_text):
    """معالجة استفسارات العملاء وإرجاع الرد المناسب"""
    return "شكراً لتواصلك! كيف يمكنني مساعدتك؟"
