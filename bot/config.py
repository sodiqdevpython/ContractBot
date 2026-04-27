import os

# Docker ichida ishlasa, telegram bot tokenini muhitdan olamiz
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8637787409:AAGH7zMMS4hjTFo9rsh4ZbKPmdJP2JKIXPE")

# Django loyiha URL manzili (Agar lokal bo'lsa localhost, Dockerda bo'lsa web)
BASE_API_URL = os.environ.get("API_BASE_URL", "http://web:8000/api/")