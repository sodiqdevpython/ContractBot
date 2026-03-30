import os
from celery import Celery
from celery.schedules import crontab

# Django sozlamalarini celery uchun standart qilib belgilaymiz
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings') # "core" ni o'zgartiring

app = Celery('core')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Har kuni soat 09:00 da qarzni eslatuvchi taskni ishga tushirish (Celery Beat)
app.conf.beat_schedule = {
    'send-daily-debt-notifications': {
        'task': 'users.tasks.send_daily_notifications', # "users" o'rnida o'zingizning app nomingiz bo'lishi kerak
        'schedule': crontab(minute='*'), # HAR DAQIQADA ISHLAYDI
    }
}