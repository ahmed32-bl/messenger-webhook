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
from deepseek import DeepSeek  # ✅ استدعاء DeepSeek لتحليل الردود

# ============ إعداد التطبيق ============
app = Flask(__name__)

# ============ مفاتيح البيئة ============
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

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

# ============ DeepSeek لتحليل الردود ============
def analyze_reply_with_deepseek(reply):
    response = DeepSeek.chat(
        api_key=DEEPSEEK_API_KEY,
        messages=[
            {"role": "system", "content": "أنت مساعد افتراضي ذكي تحلل ردود المستخدمين لتحديد إذا كانوا رجال أو نساء أو غير واضح فقط من خلال محتوى الجواب. جاوب فقط بكلمة: راجل أو مرا أو غير واضح."},
            {"role": "user", "content": f"{reply}"},
        ]
    )
    return response["choices"][0]["message"]["content"].strip()



