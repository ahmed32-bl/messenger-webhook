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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# إعداد أسماء الجداول (لـ Airtable)
CONVERSATIONS_TABLE = "Conversations"
WORKERS_TABLE = "Liste_Couturiers"

# تهيئة تطبيق Flask
app = Flask(__name__)

#########################################
# الجزء 1: نظام RAG باستخدام OpenAI
#########################################

from langchain.embeddings import OpenAIEmbeddings
embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)

from langchain.vectorstores import FAISS
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

# تحميل ملفات JSON وتحويلها إلى مستندات
def load_documents_from_json(folder_path: str) -> List[Document]:
    if not os.path.isdir(folder_path):
        raise NotADirectoryError(f"❌ المجلد '{folder_path}' غير موجود أو ليس مجلدًا فعليًا.")

    documents = []
    for filename in os.listdir(folder_path):
        if filename.endswith('.json'):
            file_path = os.path.join(folder_path, filename)
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                for entry in data:
                    text = entry.get("conversation", "")
                    doc = Document(page_content=text, metadata={'filename': filename})
                    documents.append(doc)
    return documents

# تحديد المجلد
JSON_FOLDER = "titre/json"

# بناء المستندات
documents = load_documents_from_json(JSON_FOLDER)
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
chunks = text_splitter.split_documents(documents)
vector_store = FAISS.from_documents(chunks, embeddings)
retriever = vector_store.as_retriever(search_kwargs={"k": 3})

from langchain.llms import OpenAI
from langchain.chains import RetrievalQA
llm = OpenAI(api_key=OPENAI_API_KEY, temperature=0.0)
qa_chain = RetrievalQA(llm=llm, retriever=retriever)

#########################################
# الجزء 2: استخدام DeepSeek
#########################################

def get_deepseek_response(context: str, user_message: str, rag_answer: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

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
   -إذا كان رجلًا، اجمع معلوماته (الاسم، الخبرة، نوع الملابس التي خيطها، توفر دروات وسورجي)  حسب الجدول لكن ليس دفعة واحدة .
   - إذا كانت امرأة، لا تسأل عن اسمها بل سجّل اسم الفيسبوك تلقائيًا.
2. اجمع المعلومات التالية للكل:
   - عدد سنوات الخبرة.
   - أنواع الملابس التي سبق خياطتها.
   - التأكد من وجود دروات وسورجي فقط.
3. لا تسأل المرأة عن رقم القريب إلا بعد جمع كل المعلومات.
4. عند طلب الرقم، اشرح لها أن الورشة تُرسل قطعة للتجربة ويستلمها قريبها الرجل.
5. لا تسأل عن اسم القريب حتى تحصل على الرقم.
6. إذا قال المستخدم "لم أفهم" أو "أعد": أعد شرح نفس النقطة بشكل مبسط.

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
# الجزء 3: توليد الرد النهائي
#########################################

def generate_response(user_message: str) -> str:
    rag_answer = qa_chain.run(user_message)
    relevant_docs = retriever.get_relevant_documents(user_message)
    context = "\n".join([doc.page_content for doc in relevant_docs])
    deepseek_answer = get_deepseek_response(context, user_message, rag_answer)
    return deepseek_answer

#########################################
# الجزء 4: Airtable + ماسنجر
#########################################

def get_conversation_history(sender_id):
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
    conversation = get_conversation_history(sender_id)
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{CONVERSATIONS_TABLE}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
    if conversation:
        record_id = conversation["id"]
        old_history = conversation["fields"].get("conversation_history", "")
        new_history = old_history + f"\n\U0001F464 المستخدم: {user_message}\n\U0001F916 البوت: {bot_response}"
        data = {"fields": {
            "conversation_history": new_history,
            "Dernier_Message": user_message,
            "Date_Dernier_Contact": str(datetime.now().date())
        }}
        requests.patch(f"{url}/{record_id}", json=data, headers=headers)
    else:
        data = {"records": [{"fields": {
            "Messenger_ID": sender_id,
            "conversation_history": f"\U0001F464 المستخدم: {user_message}\n\U0001F916 البوت: {bot_response}",
            "Dernier_Message": user_message,
            "Date_Dernier_Contact": str(datetime.now().date())
        }}]}
        requests.post(url, json=data, headers=headers)

def send_message(recipient_id, message_text):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {PAGE_ACCESS_TOKEN}"}
    payload = {"recipient": {"id": recipient_id}, "message": {"text": message_text}}
    requests.post("https://graph.facebook.com/v18.0/me/messages", headers=headers, json=payload)

def process_message(sender_id, user_message):
    conversation = get_conversation_history(sender_id)
    chat_history = ""
    if conversation and "fields" in conversation:
        chat_history = conversation["fields"].get("conversation_history", "")
    bot_response = generate_response(user_message)
    send_message(sender_id, bot_response)
    save_conversation(sender_id, user_message, bot_response)

#########################################
# Webhook
#########################################

@app.route("/webhook", methods=["POST"])
def webhook_post():
    try:
        data = request.get_json()
        for entry in data.get("entry", []):
            for message_data in entry.get("messaging", []):
                sender_id = message_data["sender"]["id"]
                if "message" in message_data:
                    user_message = message_data["message"].get("text", "")
                    logging.info(f"\U0001F4E9 رسالة من {sender_id}: {user_message}")
                    process_message(sender_id, user_message)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error(f"⚠️ خطأ أثناء المعالجة: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/webhook", methods=["GET"])
def webhook_get():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Error: invalid verification token"

#########################################
# تشغيل الخادم
#########################################
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)



