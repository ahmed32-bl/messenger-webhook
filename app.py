import os
import json
import requests
from flask import Flask, request, jsonify
from datetime import datetime
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain.chains import RetrievalQA
from openai import OpenAI

# ============ إعداد التطبيق ============
app = Flask(__name__)

# ============ مفاتيح البيئة ============
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

# ============ إعداد RAG بـ OpenAI ============
embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)

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

docs = load_documents_from_json("titre/json")
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
chunks = text_splitter.split_documents(docs)
vector_store = FAISS.from_documents(chunks, embeddings)
retriever = vector_store.as_retriever()
qa_chain = RetrievalQA.from_chain_type(llm=ChatOpenAI(api_key=OPENAI_API_KEY), retriever=retriever)

# ============ GPT-3.5 لتحليل الرد وفهم المعنى ============
def analyze_with_gpt(text):
    prompt = f"""
أنت مساعد ذكي، عندك حوار مع خياط، هدفك هو استخراج جنس الشخص من الردود:
- إذا قال أنه راجل أو لمح بذلك، جاوب بـ: راجل
- إذا قال أنه مرا أو لمح بذلك، جاوب بـ: مرا
- إذا كان غير واضح، جاوب بـ: غير واضح

النص: {text}
النوع:
"""
    response = OpenAI(api_key=OPENAI_API_KEY).chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content.strip()

# تابع بقية الكود هنا...


# ============ إرسال رسالة عبر فيسبوك ============
def send_message(sender_id, text):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": sender_id},
        "message": {"text": text}
    }
    requests.post(url, json=payload)

# ============ نقطة استقبال Webhook ============
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
        user = create_new_user(sender_id, "")
        if not user:
            return "ok"
        record_id = user["id"]
        create_conversation_record(sender_id, record_id, message)
        send_message(sender_id, "وعليكم السلام، مرحبا بيك في ورشة الخياطة عن بعد. نخدمو مع خياطين من وهران فقط، ونجمعو بعض المعلومات باش نشوفو إذا نقدرو نخدمو مع بعض. نبدأو وحدة بوحدة.")
        send_message(sender_id, "معليش نعرف إذا راني نتكلم مع راجل ولا مرا؟")
        return "ok"

    record_id = user["id"]
    fields = user["fields"]

    if not fields.get("Genre"):
        genre_detected = analyze_with_gpt(message)
        if genre_detected in ["راجل", "مرا"]:
            update_user_field(record_id, "Genre", genre_detected)
            user = search_user_by_messenger_id(sender_id)
            fields = user["fields"]
            send_message(sender_id, "وين تسكن فالضبط في وهران؟")
        else:
            send_message(sender_id, "معليش نعرف إذا راني نتكلم مع راجل ولا مرا؟")
        return "ok"

    if not fields.get("Ville"):
        update_user_field(record_id, "Ville", "وهران")
        update_user_field(record_id, "Quartier", message)
        user = search_user_by_messenger_id(sender_id)
        fields = user["fields"]
        send_message(sender_id, "عندك خبرة من قبل في خياطة السروال نصف الساق ولا السرفات؟")
        return "ok"

    if not fields.get("Experience_Sirwat"):
        if any(x in message for x in ["نعم", "واه", "خدمت", "عندي", "بدعيات"]):
            update_user_field(record_id, "Experience_Sirwat", True)
            user = search_user_by_messenger_id(sender_id)
            fields = user["fields"]
            send_message(sender_id, "شحال تقدر تخيط من سروال نصف الساق في السيمانة؟")
        else:
            send_message(sender_id, "نعتذرو، لازم تكون عندك خبرة في خياطة السروال ولا السرفات.")
        return "ok"

    if not fields.get("Capacite_Hebdomadaire"):
        update_user_field(record_id, "Capacite_Hebdomadaire", message)
        user = search_user_by_messenger_id(sender_id)
        fields = user["fields"]
        send_message(sender_id, "عندك سورجي؟")
        return "ok"

    if not fields.get("Surjeteuse"):
        if any(x in message for x in ["نعم", "واه", "عندي"]):
            update_user_field(record_id, "Surjeteuse", True)
        else:
            update_user_field(record_id, "Surjeteuse", False)
        user = search_user_by_messenger_id(sender_id)
        fields = user["fields"]
        send_message(sender_id, "عندك دورات وسورجي؟")
        return "ok"

    # ✅ في حال المستخدم رجع يحكي بعد التوقف، يكمل من آخر خانة ناقصة
    if fields.get("Surjeteuse"):
        send_message(sender_id, "راهي المعلومات كاملة عندنا. إذا كاين حاجة جديدة ولا تحب تزيد حاجة، قولها.")
    else:
        send_message(sender_id, "نكملو وين حبست، عاود جاوب على آخر سؤال من فضلك")
    return "ok"

# ============ تشغيل التطبيق ============
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)



