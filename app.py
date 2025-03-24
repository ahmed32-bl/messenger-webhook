import os
import json
import requests
from flask import Flask, request, jsonify
from typing import List
from datetime import datetime
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

# ---------------------------------------------
# إعداد متغيرات البيئة
# ---------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
CONV_TABLE = "Conversations"
WORKER_TABLE = "Liste_Couturiers"
HEADERS = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}

# ---------------------------------------------
# إعداد Flask
# ---------------------------------------------
app = Flask(__name__)

# ---------------------------------------------
# تحميل ملفات JSON وتحويلها إلى Documents
# ---------------------------------------------
def load_documents_from_json(folder_path: str) -> List[Document]:
    documents = []
    for filename in os.listdir(folder_path):
        if filename.endswith(".json"):
            with open(os.path.join(folder_path, filename), 'r', encoding='utf-8') as file:
                data = json.load(file)
                for entry in data:
                    text = entry.get("conversation", "")
                    documents.append(Document(page_content=text, metadata={"filename": filename}))
    return documents

# ---------------------------------------------
# إعداد RAG باستخدام OpenAI + FAISS
# ---------------------------------------------
documents = load_documents_from_json("titre/json")
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
chunks = text_splitter.split_documents(documents)
embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)
vectorstore = FAISS.from_documents(chunks, embeddings)
retriever = vectorstore.as_retriever()
qa_chain = RetrievalQA.from_chain_type(retriever=retriever, chain_type="stuff")

# ---------------------------------------------
# 📌 PROMPT داخلي للبوت (شرح مهمته)
# ---------------------------------------------
SYSTEM_PROMPT = """
انت بوت محترف تابع لورشة خياطة في وهران، تتكلم فقط بالدارجة الجزائرية.
مهمتك تستقبل الخياطين الجدد، تفهم معاهم وتجمع معلوماتهم وتخزنهم في Airtable في جدول "Liste_Couturiers".
المعلومات اللي لازم تجمعها منظمة في مراحل ومرقمة حسب الجدول، وكل مرة تراجع وش موجود قبل ما تطرح سؤال جديد.
ما تطرحش زوج أسئلة مع بعض، تمشي خطوة بخطوة، تبدأ بالترحيب وتشرح طريقة العمل، ومن بعد تسقسي سؤال بسؤال حسب الجدول.
إذا كانت المعلومات ناقصة، تكمل تسقسي، وإذا كان العامل ماشي مناسب، تعتذر باحترام.
"""

# ---------------------------------------------
# ⚡️ نهاية API: /query
# ---------------------------------------------
@app.route("/query", methods=["POST"])
def query():
    data = request.get_json()
    query_text = data.get("query")
    if not query_text:
        return jsonify({"error": "ماكانش سؤال !"}), 400

    # إرسال السؤال لـ RAG مع برومبت واضح
    full_prompt = f"{SYSTEM_PROMPT}\n\nسؤال الخياط: {query_text}"
    try:
        response = qa_chain.run(full_prompt)
        return jsonify({"answer": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------
# 🚀 تشغيل الخادم
# ---------------------------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)




