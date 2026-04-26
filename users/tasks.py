from celery import shared_task
import requests
import os
from django.utils import timezone
from .models import Student, NotificationCampaign

TELEGRAM_BOT_TOKEN = "8637787409:AAGH7zMMS4hjTFo9rsh4ZbKPmdJP2JKIXPE"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

def send_telegram_message(chat_id, text):
    if not chat_id:
        print("❌ XATOLIK: chat_id topilmadi!")
        return
        
    print(f"Bajarilmoqda: {chat_id} raqamiga xabar yuborish... Token: {TELEGRAM_BOT_TOKEN[:10]}...")
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    response = requests.post(TELEGRAM_API_URL, json=payload)
    
    # Telegramdan kelgan aniq javobni terminalga chiqaramiz:
    print(f"Telegram API javobi: {response.status_code} - {response.text}")

@shared_task
def send_otp_to_telegram(chat_id, otp_code):
    # h1 tegini code tegiga o'zgartirdik
    text = f"🔐 <b>Sizning tasdiqlash kodingiz:</b>\n\n<code>{otp_code}</code>\n\nIltimos, bu kodni farzandingizga ayting. Kod 3 daqiqa davomida amal qiladi."
    send_telegram_message(chat_id, text)

@shared_task
def send_daily_notifications():
    now_local = timezone.localtime(timezone.now())
    today = now_local.date()
    
    # Faqat bugungi kunga to'g'ri keladigan kompaniyalarni olamiz
    active_campaigns = NotificationCampaign.objects.filter(
        start_date__lte=today,
        end_date__gte=today
    )
    
    for campaign in active_campaigns:
        # 1. VAQTNI TEKSHIRISH (Bitta vaqt, shuning uchun to'g'ridan to'g'ri tekshiramiz)
        if campaign.send_time.hour == now_local.hour and campaign.send_time.minute == now_local.minute:
            
            # 2. GURUHLARNI VA GRANT/KONTRAKTNI TEKSHIRISH
            groups = campaign.groups.all()
            students_query = Student.objects.filter(group__in=groups)
            
            if campaign.student_type_filter == 'contract_only':
                students_query = students_query.filter(is_grant=False)
            elif campaign.student_type_filter == 'grant_only':
                students_query = students_query.filter(is_grant=True)

            for student in students_query:
                send_message = False
                
                # 3. QARZNI TEKSHIRISH VA FOIZLARNI HISOBLASH
                if campaign.target_debt_tier == 0:
                    send_message = True # E'lon bo'lsa hammaga boradi
                elif student.total_contract_amount > 0:
                    # Talab qilingan summa (masalan: jami summaning 50% i)
                    required_amount = (student.total_contract_amount * campaign.target_debt_tier) / 100
                    
                    if student.paid_amount < required_amount:
                        send_message = True
                
                if send_message:
                    # Tutor tasdiqlagan bo'lsa — xabarnoma yuborilmaydi
                    from dashboard.models import TutorPaymentConfirmation
                    has_suppression = TutorPaymentConfirmation.objects.filter(
                        contract__student=student,
                        is_active=True
                    ).exists()
                    if has_suppression:
                        continue

                    # Xabar matnini shakllantirish
                    text = f"⚠️ <b>Sizga yangi xabar keldi:</b>\n\n"
                    text += f"Hurmatli <b>{student.full_name}</b>,\n"
                    text += f"<i>{campaign.message_text}</i>\n\n"
                    
                    if campaign.target_debt_tier > 0 and student.total_contract_amount > 0:
                        required_amount = (student.total_contract_amount * campaign.target_debt_tier) / 100
                        debt_for_tier = required_amount - student.paid_amount
                        
                        # Hozirgacha necha foiz to'laganini hisoblab topamiz
                        current_percentage = (student.paid_amount / student.total_contract_amount) * 100
                        
                        text += f"💳 <b>Umumiy kontrakt:</b> {student.total_contract_amount:,.0f} so'm\n"
                        text += f"✅ <b>To'langan summa:</b> {student.paid_amount:,.0f} so'm <i>({current_percentage:.1f}%)</i>\n"
                        text += f"🛑 <b>Shu muddatni yopish uchun to'lashingiz kerak:</b> {debt_for_tier:,.0f} so'm\n"

                    # 4. KIMGA YUBORISH
                    if campaign.recipients in ['student_only', 'student_and_parent']:
                        send_telegram_message(student.telegram_id, text)
                        
                    if campaign.recipients in ['parent_only', 'student_and_parent']:
                        verified_parents = student.parents.filter(status='verified')
                        for relation in verified_parents:
                            parent_text = text.replace(f"Hurmatli <b>{student.full_name}</b>", f"Hurmatli ota-ona, farzandingiz <b>{student.full_name}</b> uchun")
                            send_telegram_message(relation.parent.telegram_id, parent_text)