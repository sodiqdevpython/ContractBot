from celery import shared_task
import requests
from django.utils import timezone
from .models import Student, NotificationCampaign

TELEGRAM_BOT_TOKEN = "8637787409:AAGH7zMMS4hjTFo9rsh4ZbKPmdJP2JKIXPE"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"


def send_telegram_message(chat_id, text, student=None, parent=None, campaign=None, is_otp=False):
    """
    Telegram ga xabar yuboradi.
    - Muvaffaqiyatli bo'lsa: eski NotificationFailure yozuvini o'chiradi.
    - Muvaffaqiyatsiz bo'lsa: NotificationFailure yaratadi yoki yangilaydi.
    """
    if not chat_id:
        print("❌ XATOLIK: chat_id topilmadi!")
        return False

    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    try:
        response = requests.post(TELEGRAM_API_URL, json=payload, timeout=10)
        result = response.json()
    except Exception as e:
        print(f"❌ So'rov xatosi: {e}")
        _log_failure(chat_id, str(e), None, student, parent, campaign, is_otp)
        return False

    print(f"Telegram API: {chat_id} → {response.status_code} {response.text[:120]}")

    if result.get('ok'):
        # Muvaffaqiyatli — eski xato yozuvini o'chiramiz
        recipient_type = 'student' if student else 'parent'
        _clear_failure(chat_id, recipient_type)
        return True
    else:
        err_code = result.get('error_code')
        err_desc = result.get('description', 'Noma\'lum xato')
        _log_failure(chat_id, err_desc, err_code, student, parent, campaign, is_otp)
        return False


def _log_failure(chat_id, description, error_code, student, parent, campaign, is_otp):
    """NotificationFailure ga yozadi yoki fail_count ni oshiradi."""
    from dashboard.models import NotificationFailure
    recipient_type = 'student' if student else 'parent'
    obj, created = NotificationFailure.objects.get_or_create(
        telegram_id=chat_id,
        recipient_type=recipient_type,
        defaults={
            'student': student,
            'parent': parent,
            'error_code': error_code,
            'error_description': description,
            'campaign': campaign,
            'is_otp': is_otp,
            'fail_count': 1,
        }
    )
    if not created:
        obj.fail_count += 1
        obj.error_code = error_code
        obj.error_description = description
        if campaign:
            obj.campaign = campaign
        obj.save(update_fields=['fail_count', 'error_code', 'error_description', 'campaign', 'last_failed_at'])


def _clear_failure(chat_id, recipient_type):
    """Muvaffaqiyatli xabardan keyin xato yozuvini o'chiramiz."""
    from dashboard.models import NotificationFailure
    NotificationFailure.objects.filter(
        telegram_id=chat_id, recipient_type=recipient_type
    ).delete()


@shared_task
def send_otp_to_telegram(chat_id, otp_code):
    text = (
        f"🔐 <b>Sizning tasdiqlash kodingiz:</b>\n\n"
        f"<code>{otp_code}</code>\n\n"
        f"Iltimos, bu kodni farzandingizga ayting. Kod 3 daqiqa davomida amal qiladi."
    )
    send_telegram_message(chat_id, text, is_otp=True)


@shared_task
def send_daily_notifications():
    now_local = timezone.localtime(timezone.now())
    today = now_local.date()

    active_campaigns = NotificationCampaign.objects.filter(
        start_date__lte=today,
        end_date__gte=today
    )

    for campaign in active_campaigns:
        if campaign.send_time.hour != now_local.hour or campaign.send_time.minute != now_local.minute:
            continue

        groups = campaign.groups.all()
        students_query = Student.objects.filter(group__in=groups)

        if campaign.student_type_filter == 'contract_only':
            students_query = students_query.filter(contracts__is_grant=False).distinct()
        elif campaign.student_type_filter == 'grant_only':
            students_query = students_query.filter(contracts__is_grant=True).distinct()

        for student in students_query:
            send_message = False

            if campaign.target_debt_tier == 0:
                send_message = True
            elif student.total_contract_amount > 0:
                required_amount = (student.total_contract_amount * campaign.target_debt_tier) / 100
                if student.paid_amount < required_amount:
                    send_message = True

            if not send_message:
                continue

            # Tutor tasdiqlagan bo'lsa — xabarnoma yuborilmaydi
            from dashboard.models import TutorPaymentConfirmation
            if TutorPaymentConfirmation.objects.filter(
                contract__student=student, is_active=True
            ).exists():
                continue

            # Xabar matni
            text = f"⚠️ <b>Sizga yangi xabar keldi:</b>\n\nHurmatli <b>{student.full_name}</b>,\n"
            text += f"<i>{campaign.message_text}</i>\n\n"

            if campaign.target_debt_tier > 0 and student.total_contract_amount > 0:
                required_amount = (student.total_contract_amount * campaign.target_debt_tier) / 100
                debt_for_tier = required_amount - student.paid_amount
                pct = (student.paid_amount / student.total_contract_amount) * 100
                text += f"💳 <b>Umumiy kontrakt:</b> {student.total_contract_amount:,.0f} so'm\n"
                text += f"✅ <b>To'langan summa:</b> {student.paid_amount:,.0f} so'm <i>({pct:.1f}%)</i>\n"
                text += f"🛑 <b>To'lashingiz kerak:</b> {debt_for_tier:,.0f} so'm\n"

            if campaign.recipients in ['student_only', 'student_and_parent']:
                send_telegram_message(
                    student.telegram_id, text,
                    student=student, campaign=campaign
                )

            if campaign.recipients in ['parent_only', 'student_and_parent']:
                for relation in student.parents.filter(status='verified').select_related('parent'):
                    parent_text = text.replace(
                        f"Hurmatli <b>{student.full_name}</b>",
                        f"Hurmatli ota-ona, farzandingiz <b>{student.full_name}</b> uchun"
                    )
                    send_telegram_message(
                        relation.parent.telegram_id, parent_text,
                        parent=relation.parent, campaign=campaign
                    )
