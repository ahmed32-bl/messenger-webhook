############################################################
# app.py
# هذا الملف يدمج بوت ماسنجر مع نظام RAG.
# يستخدم OpenAI (أو بديل مفتوح المصدر) لإنتاج الـEmbeddings وبناء نظام الاسترجاع (RAG)،
# ثم يستخدم DeepSeek لتوليد الرد النهائي.
############################################################

import os
import json
import requests
import logging
from datetime import datetime
from typing import List

from flask import Flask, request, jsonify

# إعداد سجل التتبع
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# تحميل متغيرات البيئة
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")         # لاستخدامه في نظام RAG (Embeddings، استرجاع)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")     # لاستخدام DeepSeek في التوليد

# إعداد أسماء الجداول (لـ Airtable)
CONVERSATIONS_TABLE = "Conversations"
WORKERS_TABLE = "Liste_Couturiers"

# تهيئة تطبيق Flask
app = Flask(__name__)

#########################################
# الجزء 1: نظام RAG باستخدام OpenAI
#########################################

# 1) إنشاء Embeddings باستخدام OpenAI
from langchain.embeddings import OpenAIEmbeddings
embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)
# (يمكنك استبدالها بـ HuggingFaceEmbeddings إذا رغبت)

# 2) إنشاء مخزن المتجهات باستخدام FAISS
from langchain.vectorstores import FAISS

# 3) دالة لتحميل ملفات JSON وتحويلها إلى Documents
from langchain.schema import Document
def load_documents_from_json(folder_path: str) -> List[Document]:
    """
    تقرأ جميع ملفات JSON في المجلد المحدد وتحول كل عنصر (entry) إلى Document.
    نفترض أن كل ملف JSON يحتوي على قائمة من الكائنات، وكل كائن يحوي حقل "conversation".
    """
    documents = []
    for filename in os.listdir(folder_path):
        if filename.endswith('.json'):
            file_path = os.path.join(folder_path, filename)
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                for entry in data:
                    text = entry.get("conversation", "")  # تأكد من أن حقل "conversation" موجود في ملفاتك
                    doc = Document(page_content=text, metadata={'filename': filename})
                    documents.append(doc)
    return documents

# 4) تحديد المجلد الذي يحوي ملفات JSON داخل المشروع (مثلاً "titre")
JSON_FOLDER = "titre"

# 5) تحميل المستندات
documents = load_documents_from_json(JSON_FOLDER)

# 6) تقسيم المستندات إلى مقاطع (Chunking) لتحسين عملية الاسترجاع
from langchain.text_splitter import RecursiveCharacterTextSplitter
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
chunks = text_splitter.split_documents(documents)

# 7) إنشاء الـVector Store من المستندات والـEmbeddings
#    بدلاً من استخدام embedding_dimension في __init__، نستعمل from_documents:
vector_store = FAISS.from_documents(chunks, embeddings)

# 8) إنشاء أداة الاسترجاع (Retriever) من مخزن المتجهات
retriever = vector_store.as_retriever(search_kwargs={"k": 3})

# 9) إنشاء سلسلة الاسترجاع والتوليد (RetrievalQA) باستخدام نموذج OpenAI
from langchain.llms import OpenAI
llm = OpenAI(api_key=OPENAI_API_KEY, temperature=0.0)
from langchain.chains import RetrievalQA
qa_chain = RetrievalQA(llm=llm, retriever=retriever)

#########################################
# الجزء 2: استخدام DeepSeek لتوليد الرد
#########################################

def get_deepseek_response(context: str, user_message: str, rag_answer: str) -> str:
    """
    تستخدم هذه الدالة DeepSeek لتوليد رد نهائي بناءً على:
    - السياق المسترجع (context) من نظام RAG.
    - الإجابة المبدئية من RAG (rag_answer).
    - رسالة المستخدم (user_message).

    ندمجها في برومبت متكامل يوضّح لDeepSeek دوره كمساعد آلي متخصص في ورشة الخياطة.
    """
    from openai import OpenAI  # نستخدم مكتبة openai مع تغيير base_url لـ DeepSeek
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

    # برومبت متكامل (وفق ما اتفقنا عليه)
    prompt = f"""سياق النصوص المسترجعة:
{context}

إجابة نظام RAG (مبدئية):
{rag_answer}

تعليمات:
- أنت مساعد آلي متخصص في ورشة الخياطة.
📌 دورك:
أنت مساعد آلي خاص بورشة خياطة، تتحدث باللهجة الجزائرية فقط بأسلوب محترم وأخوي.
مهمتك جمع المعلومات الضرورية فقط من العامل/العاملة دون الخروج عن الموضوع.

✅ التعليمات الأساسية:
1. ابدأ بسؤال العامل عن جنسه:
   - إذا كان رجلًا، اجمع معلوماته (الاسم، الخبرة، نوع الملابس التي خيطها، توفر دروات وسورجي) مباشرة.
   - إذا كانت امرأة، لا تسأل عن اسمها بل سجّل اسم الفيسبوك تلقائيًا.
2. اجمع المعلومات التالية للكل (رجل أو امرأة):
   - عدد سنوات الخبرة في الخياطة.
   - أنواع الملابس التي سبق خياطتها (خصوصًا سروال نصف الساق أو السيرفات).
   - التأكد من وجود دروات وسورجي فقط.
3. لا تسأل المرأة عن رقم القريب إلا بعد جمع كل المعلومات أعلاه.
4. عند طلب رقم القريب، اشرح لها أن الورشة تُرسل أول قطعة للتجربة، ويجب أن يتسلمها قريبها الرجل. 
   إذا تم التأكد من جودة العمل، تُرسل لاحقًا كمية تكفي لأسبوع.
5. لا تسأل عن اسم القريب حتى تحصل على الرقم الرقم. 
6. إذا قال المستخدم "لم أفهم" أو "أعد" أو كرر نفس الطلب:
   - أعد شرح نفس النقطة دون نسخ الرد السابق حرفيًا.
- يجب عليك اتباع التعليمات بدقة وتقديم ردود واضحة ومفصلة.
- استخدم أسلوباً مهذباً ومهنياً في الإجابات.
- يمكنك الاستعانة بالإجابة المبدئية من نظام RAG، مع تصحيح أي أخطاء أو إضافة معلومات ضرورية.

رسالة المستخدم:
{user_message}

الرجاء تقديم الرد النهائي بناءً على التعليمات والسياق أعلاه:
"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "أنت مساعد آلي متخصص في ورشة الخياطة وتتبع تعليمات محددة."},
            {"role": "user", "content": prompt}
        ],
        stream=False
    )
    return response.choices[0].message.content.strip()

#########################################
# الجزء 3: دمج نظام RAG مع بوت ماسنجر
#########################################

def generate_response(user_message: str) -> str:
    """
    1) نحصل على إجابة مبدئية من RAG (qa_chain).
    2) نسترجع النصوص ذات الصلة من الـVector Store كـ"سياق".
    3) نمرر الإجابة المبدئية والسياق والرسالة الأصلية إلى DeepSeek للحصول على الرد النهائي.
    """
    # 1) الحصول على الرد المبدئي باستخدام RAG
    rag_answer = qa_chain.run(user_message)
    
    # 2) استرجاع نصوص ذات صلة من الـVector Store
    relevant_docs = retriever.get_relevant_documents(user_message)
    context = "\n".join([doc.page_content for doc in relevant_docs])
    
    # 3) الحصول على الرد النهائي من DeepSeek
    deepseek_answer = get_deepseek_response(context, user_message, rag_answer)
    
    # إعادة الرد النهائي
    return deepseek_answer

#########################################
# الجزء 4: دوال Airtable وبوت ماسنجر
#########################################

def get_conversation_history(sender_id):
    """ استرجاع سجل المحادثات السابقة من Airtable (اختياري) """
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{CONVERSATIONS_TABLE}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        records = response.json().get("records", [])
        for record in records:
            if record["fields"].get("Messenger_ID") == sender_id:
                return record
    return None

def save_conversation(sender_id, user_message, bot_response):
    """ حفظ المحادثة في Airtable (اختياري) """
    conversation = get_conversation_history(sender_id)
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{CONVERSATIONS_TABLE}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    if conversation:
        record_id = conversation["id"]
        old_history = conversation["fields"].get("conversation_history", "")
        new_history = old_history + f"\n👤 المستخدم: {user_message}\n🤖 البوت: {bot_response}"
        data = {
            "fields": {
                "conversation_history": new_history,
                "Dernier_Message": user_message,
                "Date_Dernier_Contact": str(datetime.now().date())
            }
        }
        url_update = f"{url}/{record_id}"
        requests.patch(url_update, json=data, headers=headers)
    else:
        data = {
            "records": [
                {
                    "fields": {
                        "Messenger_ID": sender_id,
                        "conversation_history": f"👤 المستخدم: {user_message}\n🤖 البوت: {bot_response}",
                        "Dernier_Message": user_message,
                        "Date_Dernier_Contact": str(datetime.now().date())
                    }
                }
            ]
        }
        requests.post(url, json=data, headers=headers)

def send_message(recipient_id, message_text):
    """ إرسال رد إلى المستخدم عبر Facebook Messenger """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {PAGE_ACCESS_TOKEN}"
    }
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    requests.post("https://graph.facebook.com/v18.0/me/messages", headers=headers, json=payload)

def process_message(sender_id, user_message):
    """ معالجة رسالة من المستخدم """
    conversation = get_conversation_history(sender_id)
    chat_history = ""
    if conversation and "fields" in conversation:
        chat_history = conversation["fields"].get("conversation_history", "")
    
    # الحصول على الرد النهائي من نظام RAG + DeepSeek
    bot_response = generate_response(user_message)
    
    # إرسال الرد إلى المستخدم
    send_message(sender_id, bot_response)
    
    # حفظ المحادثة في Airtable (اختياري)
    save_conversation(sender_id, user_message, bot_response)

#########################################
# مسارات Webhook لبوت ماسنجر
#########################################

@app.route("/webhook", methods=["POST"])
def webhook_post():
    """ استقبال ومعالجة رسائل ماسنجر """
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

@app.route("/webhook", methods=["GET"])
def webhook_get():
    """ تحقق من VERIFY_TOKEN عند إعداد Webhook في فيسبوك """
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Error: invalid verification token"

#########################################
# تشغيل التطبيق
#########################################
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)



