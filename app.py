import os
import requests
from flask import Flask, request, jsonify
import openai

# 📌 تهيئة التطبيق Flask
# هذا التطبيق يعمل كـ webhook للتفاعل مع Messenger
app = Flask(__name__)

# 📌 مفاتيح API والإعدادات
VERIFY_TOKEN = "workshop_chatbot_123"  # رمز التحقق من ال webhook مع Messenger
PAGE_ACCESS_TOKEN = "PAGE_ACCESS_TOKEN"  # مفتاح API لإرسال الرسائل عبر Messenger
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # مفتاح API لـ GPT-4
AIRTABLE_API_KEY = "AIRTABLE_API"  # مفتاح API لـ Airtable
AIRTABLE_BASE_ID = "AIRTABLE_BASE_ID"
TABLE_PRODUITS = "Produits"  # اسم جدول المنتجات
TABLE_COMMANDES = "Commandes"  # اسم جدول الطلبات
TABLE_CLIENTS = "Clients"  # اسم جدول العملاء
TABLE_FAQ = "FAQ"  # جدول الأسئلة الشائعة
ADMIN_ID = "503020996238881"  # معرف المسؤول لاستلام الإشعارات
