import os
import requests
from flask import Flask, request, jsonify
import openai
from dotenv import load_dotenv  # 📌 Importer dotenv

# 🔹 Charger les variables depuis le fichier .env
load_dotenv()

# 🔹 Initialisation Flask
app = Flask(__name__)

# 🔹 Chargement des variables API depuis .env
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")

# 🔹 Noms des tables Airtable
TABLE_PRODUITS = os.getenv("TABLE_PRODUITS")
TABLE_COMMANDES = os.getenv("TABLE_COMMANDES")
TABLE_CLIENTS = os.getenv("TABLE_CLIENTS")
TABLE_FAQ = os.getenv("TABLE_FAQ")

# 🔹 ID Admin
ADMIN_ID = os.getenv("ADMIN_ID")
