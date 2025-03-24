import os
import json
import requests
from flask import Flask, request, jsonify
from datetime import datetime

# LangChain - RAG
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain.chains import RetrievalQA
from langchain_core.language_models import ChatAnthropic

# ============ Initialisation ============
app = Flask(__name__)

# ============ ENV VARS ============
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# ============ Airtable Setup ============
COUTURIERS_TABLE = "Liste_Couturiers"
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json"
}

# ============ RAG Setup (OpenAI + DeepSeek) ============
embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)

def load_documents_from_json(folder_path):
    documents = []
    for filename in os.listdir(folder_path):
        if filename.endswith(".json"):
            with open(os.path.join(folder_path, filename), 'r', encoding='utf-8') as f:
                data = json.load(f)
                for entry in data:
                    text = entry.get("conversation", "")
                    documents.append(Document(page_content=text))
    return documents

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
docs = load_documents_from_json("titre/json")
chunks = text_splitter.split_documents(docs)
vector_store = FAISS.from_documents(chunks, embeddings)
retriever = vector_store.as_retriever()

# استخدام DeepSeek كـ LLM للردود الذكية داخل RetrievalQA
qa_chain = RetrievalQA.from_chain_type(
    llm=ChatAnthropic(model="deepseek-chat", api_key=DEEPSEEK_API_KEY),
    retriever=retriever
)

# ============ Airtable Functions ============
def search_user_by_messenger_id(messenger_id):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{COUTURIERS_TABLE}?filterByFormula={{Messenger_ID}}='{messenger_id}'"
    res = requests.get(url, headers=HEADERS).json()
    return res["records"][0] if res.get("records") else None

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
    return requests.patch(url, headers=HEADERS, json=payload).json()

# ============ Facebook Messenger Send ============
def send_message(sender_id, text):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": sender_id},
        "message": {"text": text}
    }
    requests.post(url, json=payload)

# ============ Chatbot Logic ============
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
        send_message(sender_id, "\u0633\u0644\u0627\u0645 \u0648\u0631\u062d\u0645\u0629 \u0627\u0644\u0644\u0647، \u0647\u0647\u064a \u0648\u0631\u0634\u062a\u0646\u0627 \u0644\u0644\u062e\u064a\u0627\u0637\u0629 \u0639\u0646 \u0628\u0639\u062f. \u0646\u062e\u062f\u0645\u0648 \u063a\u064a \u0645\u0639 \u0644\u064a \u0641\u064a \u0648\u0647\u0631\u0627\u0646، \u0648\u0631\u062d \u0646\u0637\u0631\u062d\u0648 \u0639\u0644\u064a\u0643 \u0623\u0633\u0626\u0644\u0629 \u0648\u0627\u062d\u062f\u0629 \u0628\u0627\u0644\u0648\u0627\u062d\u062f.\n\u0628\u062f\u064a\u062a \u0627\u0644\u0623\u0648\u0644\u0649: \u0631\u0627\u0643 \u0631\u0627\u062c\u0644 \u0648\u0644\u0627 \u0645\u0631\u0627؟")
        return "ok"

    # تحقق من البيانات الناقصة
    fields = user["fields"]
    record_id = user["id"]

    if not fields.get("Genre"):
        if "راجل" in message:
            update_user_field(record_id, "Genre", "راجل")
            send_message(sender_id, "وين ساكن بالضبط في وهران؟")
        elif "مرا" in message:
            update_user_field(record_id, "Genre", "مرا")
            send_message(sender_id, "وين ساكنة بالضبط في وهران؟")
        else:
            send_message(sender_id, "باش نكمل معاك، قولي راك راجل ولا مرا؟")
        return "ok"

    if not fields.get("Ville"):
        update_user_field(record_id, "Ville", "وهران")
        update_user_field(record_id, "Quartier", message)
        send_message(sender_id, "خدمت قبل في سروال نصف الساق ولا السرفات؟")
        return "ok"

    if not fields.get("Experience_Sirwat"):
        if any(word in message for word in ["نعم", "واه", "خدمت", "ندير"]):
            update_user_field(record_id, "Experience_Sirwat", True)
            send_message(sender_id, "واش تقدر تدير فالسيمانة؟")
        else:
            send_message(sender_id, "نعتذرو، لازم تكون عندك خبرة في السروال ولا السرفات.")
        return "ok"

    if not fields.get("Capacite_Hebdomadaire"):
        update_user_field(record_id, "Capacite_Hebdomadaire", message)
        send_message(sender_id, "عندك سورجي؟")
        return "ok"

    if not fields.get("Surjeteuse"):
        update_user_field(record_id, "Surjeteuse", "واه" in message or "نعم" in message)
        send_message(sender_id, "عندك دورات؟")
        return "ok"

    send_message(sender_id, "بارك الله فيك، المعلومات راهي كاملة. نعيطولك ونتفاهو إن شاء الله.")
    return "ok"

# ============ Run ============
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
