import os
import json
import requests
from flask import Flask, request, jsonify
from datetime import datetime

# ✅ مكتبات LangChain الحديثة
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain.chains import RetrievalQA

# ✅ إعداد التطبيق
app = Flask(__name__)

# ✅ مفاتيح البيئة
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

# ✅ إعداد RAG بـ OpenAI
embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)

def load_documents_from_json(folder_path):
    documents = []
    for filename in os.listdir(folder_path):
        if filename.endswith(".json"):
            with open(os.path.join(folder_path, filename), "r", encoding="utf-8") as file:
                data = json.load(file)
                for entry in data:
                    text = entry.get("conversation", "")
                    documents.append(Document(page_content=text, metadata={"filename": filename}))
    return documents

docs = load_documents_from_json("titre/json")
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
chunks = text_splitter.split_documents(docs)
vector_store = FAISS.from_documents(chunks, embeddings)
retriever = vector_store.as_retriever()
qa_chain = RetrievalQA.from_chain_type(llm=None, retriever=retriever)

# ✅ إعداد Airtable
COUTURIERS_TABLE = "Liste_Couturiers"
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json"
}

# ✅ إرسال رسالة للعميل عبر فيسبوك
def send_message(sender_id, text):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": sender_id},
        "message": {"text": text}
    }
    requests.post(url, json=payload)

# ✅ التعامل مع Airtable

def search_user_by_messenger_id(messenger_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{COUTURIERS_TABLE}?filterByFormula={{Messenger_ID}}='{messenger_id}'"
    res = requests.get(url, headers=HEADERS)
    data = res.json()
    if data.get("records"):
        return data["records"][0]
    return None

def create_new_user(messenger_id, name=""):
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
    requests.patch(url, headers=HEADERS, json=payload)

# ✅ نقطة الاستقبال من فيسبوك
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
        create_new_user(sender_id)
        send_message(sender_id, "وعليكم السلام، مرحبا بيك في ورشة الخياطة عن بعد. نخدمو غير مع ناس وهران، ونجمعو شوية معلومات. نبداو؟ حبيت نعرف اولا اذا راني نتكلم مع راجل ولا مرا؟")
        return "ok"

    fields = user["fields"]
    record_id = user["id"]

    if not fields.get("Genre"):
        if "راجل" in message:
            update_user_field(record_id, "Genre", "راجل")
            send_message(sender_id, "وين تسكن بالضبط في وهران؟")
        elif "مرا" in message:
            update_user_field(record_id, "Genre", "مرا")
            send_message(sender_id, "وين تسكن بالضبط في وهران؟")
        else:
            send_message(sender_id, "باش نكمل معاك، قولي راك راجل ولا مرا؟")
        return "ok"

    if not fields.get("Ville"):
        update_user_field(record_id, "Ville", "وهران")
        update_user_field(record_id, "Quartier", message)
        send_message(sender_id, "عندك خبرة في السروال نصف الساق ولا السرفات؟")
        return "ok"

    if not fields.get("Experience_Sirwat"):
        if any(x in message for x in ["نعم", "واه", "خدمت"]):
            update_user_field(record_id, "Experience_Sirwat", True)
            send_message(sender_id, "شحال تقدر تخيط من سروال فالسمانة؟")
        else:
            send_message(sender_id, "نعتذرو، لازم تكون خدمتها من قبل.")
        return "ok"

    if not fields.get("Capacite_Hebdomadaire"):
        update_user_field(record_id, "Capacite_Hebdomadaire", message)
        send_message(sender_id, "عندك سورجي؟")
        return "ok"

    if not fields.get("Surjeteuse"):
        if "نعم" in message or "واه" in message:
            update_user_field(record_id, "Surjeteuse", True)
        else:
            update_user_field(record_id, "Surjeteuse", False)
        send_message(sender_id, "عندك دورات؟")
        return "ok"

    send_message(sender_id, "بارك الله فيك، نعيطولك ونتفاهمو إن شاء الله!")
    return "ok"

# ✅ تشغيل التطبيق
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)







