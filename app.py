import os
import json
import requests
from flask import Flask, request
from datetime import datetime

# LangChain - RAG (OpenAI)
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain.chains import RetrievalQA

# === إعداد Flask ===
app = Flask(__name__)

# === مفاتيح البيئة ===
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

# === تحميل بيانات JSON ===
def load_documents_from_json(folder_path):
    documents = []
    for filename in os.listdir(folder_path):
        if filename.endswith(".json"):
            path = os.path.join(folder_path, filename)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for entry in data:
                    text = entry.get("conversation", "")
                    documents.append(Document(page_content=text, metadata={"filename": filename}))
    return documents

# === إنشاء قاعدة متجهات RAG ===
docs = load_documents_from_json("titre/json")
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
chunks = text_splitter.split_documents(docs)
embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)
vector_store = FAISS.from_documents(chunks, embeddings)
retriever = vector_store.as_retriever()
qa_chain = RetrievalQA.from_chain_type(llm=ChatOpenAI(api_key=OPENAI_API_KEY), retriever=retriever)

# === إعداد Airtable ===
COUTURIERS_TABLE = "Liste_Couturiers"
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json"
}

def search_user_by_messenger_id(messenger_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{COUTURIERS_TABLE}?filterByFormula={{Messenger_ID}}='{messenger_id}'"
    res = requests.get(url, headers=HEADERS)
    data = res.json()
    return data["records"][0] if data.get("records") else None

def create_new_user(messenger_id, name):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{COUTURIERS_TABLE}"
    payload = {
        "fields": {
            "Messenger_ID": messenger_id,
            "Nom": name,
            "Date_Inscription": datetime.now().strftime("%Y-%m-%d")
        }
    }
    res = requests.post(url, headers=HEADERS, json=payload)
    return res.json()

def update_user_field(record_id, field, value):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{COUTURIERS_TABLE}/{record_id}"
    payload = {"fields": {field: value}}
    return requests.patch(url, headers=HEADERS, json=payload).json()

def send_message(recipient_id, text):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    requests.post(url, json=payload)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    event = data.get("entry", [{}])[0].get("messaging", [{}])[0]
    sender_id = event.get("sender", {}).get("id")
    message = event.get("message", {}).get("text")

    if not sender_id or not message:
        return "ok"

    user = search_user_by_messenger_id(sender_id)
    if not user:
        create_new_user(sender_id, "")
        send_message(sender_id, "وعليكم السلام، مرحبا بيك في ورشة الخياطة عن بعد. نخدمو غير مع خياطين من وهران، نطرح عليك شوية أسئلة باش نشوفو إذا نقدر نخدمو مع بعض. نبدأو وحدة بوحدة.")
        send_message(sender_id, "راك راجل ولا مرا؟")
        return "ok"

    # الخطوات التالية تعتمد على الأعمدة الموجودة في Airtable حسب الاتفاق المسبق
    fields = user["fields"]
    record_id = user["id"]

    # مثال بسيط لتحديث الحقول تدريجياً (اكمل بنفس المنطق)
    if not fields.get("Genre"):
        if "راجل" in message:
            update_user_field(record_id, "Genre", "راجل")
            send_message(sender_id, "وين تسكن فالضبط في وهران؟")
        elif "مرا" in message:
            update_user_field(record_id, "Genre", "مرا")
            send_message(sender_id, "وين تسكن فالضبط في وهران؟")
        else:
            send_message(sender_id, "باش نكمل معاك، قولنا فقط راك راجل ولا مرا؟")
        return "ok"

    # مثال على استخدام الذكاء الاصطناعي في الردود (RAG):
    if "سروال" in message or "خياطة" in message:
        result = qa_chain.run(message)
        send_message(sender_id, result)
        return "ok"

    send_message(sender_id, "شكراً على تواصلك، نكملو الأسئلة إن شاء الله! ✂️")
    return "ok"

# ============ تشغيل التطبيق ==========
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)

