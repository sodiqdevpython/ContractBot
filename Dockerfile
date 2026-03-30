FROM python:3.10-slim

# Muhit o'zgaruvchilari (Pythonda printlar to'g'ridan-to'g'ri terminalga chiqishi uchun)
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Kutubxonalarni o'rnatish
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Loyiha fayllarini ko'chirish
COPY . /app/