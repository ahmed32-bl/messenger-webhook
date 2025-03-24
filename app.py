import os
import json
from typing import List
from flask import Flask, request, jsonify
from langchain.embeddings import DeepSeekEmbeddings
from langchain.vectorstores import FAISS
from langchain.chains import RetrievalQA
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
import openai
import datetime
import airtable

# تهيئة Flask
app = Flask(__name__)

# قيم API من متغيرات البيئة
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
DEESEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# اعداد DeepSeek و OpenAI API
openai.api_key = DEESEEK_API_KEY

def create_embedding_model():
    return DeepSeekEmbeddings()

embeddings = create_embedding_model()

# نسخدم FAISS لتخزين وبحث المعرفة
vector_store = FAISS(embedding_dimension=1536)

# تحميل مستندات JSON
JSON_FOLDER = "titre/json"

def load_documents_from_json(folder_path: str) -> List[Document]:
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

documents = load_documents_from_json(JSON_FOLDER)
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
chunks = text_splitter.split_documents(documents)
vector_store.add_documents(chunks, embeddings)
retriever = vector_store.as_retriever()
qa_chain = RetrievalQA(retriever=retriever)

# إعداد Airtable
airtable_couturiers = airtable.Airtable(AIRTABLE_BASE_ID, 'Liste_Couturiers', AIRTABLE_API_KEY)

# أسئلة البوت المنظمة حسب الجدول
QUESTIONS = [
    ("Genre", "بغيت نعرف، راك راجل ولا مرا؟"),
    ("Ville", "باش نكملو، لازم تكون من وهران. واش راك من وهران؟ إذا إييه، وين بالضبط؟"),
    ("Experience_Sirwat", "سبقلك خيطت سروال نصف الساق من قبل؟"),
    ("Experience_Surjeteuse", "وعندك دراية بالخياطة بالسورجي؟"),
    ("Type_Vetements", "وش من نوع الخياطات موالف تخدم؟"),
    ("Capacite_Hebdomadaire", "شحال تقريبا تقدر تخدم من سروال نصف الساق في السيمانة؟"),
    ("Materiel_Dispo", "وشنو الماتريال لي عندك متوفر في داركم؟"),
    ("Drouat", "عندك دروات نخدمو عليهم؟"),
    ("Telephone", "عطيني رقم هاتف نخاطبك فيه."),
    ("Nom_Proche", "إلا كنت مرا، عطيني اسم شخص قريب منك (راجل) باش نقدر نتفاهمو معاه."),
    ("Contact_Proche", "ورقم الهاتف تاعو من فضلك؟")
]

# مسار API للرد
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    sender_id = data.get("sender_id")
    message = data.get("message")

    # 1. يراجع هل هذا العامل موجود في Airtable
    records = airtable_couturiers.search('Messenger_ID', sender_id)
    if records:
        record = records[0]
    else:
        # إذا ماكانش موجود، ينشيء سطر جديد
        record = airtable_couturiers.insert({
            "Messenger_ID": sender_id,
            "conversation_history": message,
            "Date_Inscription": datetime.datetime.now().strftime('%Y-%m-%d')
        })

    fields = record['fields']
    updates = {}

    # 2. يراجع المعلومات ويشوف شنو ناقص
    for field, question in QUESTIONS:
        if field not in fields or not fields[field]:
            # DeepSeek prompt to guess the value from message
            guessed_value = qa_chain.run(f"{message}\n\nوش تعني هاذ الجواب بالنسبة للحقل: {field}؟")
            if guessed_value.strip():
                updates[field] = guessed_value.strip()
                break
            else:
                return jsonify({"reply": question})

    # 3. تحديث Airtable بالمعلومات الجديدة
    if updates:
        airtable_couturiers.update(record['id'], updates)
        return jsonify({"reply": "تمام، سجلت المعلومة. نكملو؟"})

    return jsonify({"reply": "شكرا على تعاونك، نعيطولك ونتفاهو إن شاء الله!"})

# تشغيل Flask
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)





