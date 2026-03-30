from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.files.base import ContentFile
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
import random
import requests
from django.shortcuts import get_object_or_404
from .tasks import send_otp_to_telegram

from .models import Student, Parent, StudentParent
from .serializers import StudentProfileSerializer, ParentSerializer

class StudentLoginView(APIView):
    def post(self, request):
        data = request.data
        student_id = data.get('student_id')
        password = data.get('password')
        
        try:
            student = Student.objects.get(student_id=student_id, password=password)
            
            student.telegram_id = data.get('telegram_id', student.telegram_id)
            student.tg_username = data.get('tg_username', student.tg_username)
            student.tg_first_name = data.get('tg_first_name', student.tg_first_name)
            student.tg_last_name = data.get('tg_last_name', student.tg_last_name)
            student.tg_language = data.get('tg_language', student.tg_language)
            
            # RASMNI YUKLAB OLISH VA SAQLASH
            photo_url = data.get('photo_url')
            if photo_url and not student.profile_picture:
                try:
                    img_response = requests.get(photo_url)
                    if img_response.status_code == 200:
                        file_name = f"student_{student.student_id}.jpg"
                        student.profile_picture.save(file_name, ContentFile(img_response.content), save=False)
                except Exception:
                    pass

            student.save()
            serializer = StudentProfileSerializer(student)
            return Response({"success": True, "student": serializer.data}, status=status.HTTP_200_OK)
        except Student.DoesNotExist:
            return Response({"success": False, "message": "Login yoki parol xato!"}, status=status.HTTP_404_NOT_FOUND)

class TriggerOTPView(APIView):
    def post(self, request):
        sp_id = request.data.get('sp_id')
        sp = get_object_or_404(StudentParent, id=sp_id)
        
        otp = str(random.randint(100000, 999999))
        sp.otp_code = otp
        sp.otp_expires_at = timezone.now() + timedelta(minutes=3)
        sp.save()
        
        send_otp_to_telegram.delay(sp.parent.telegram_id, otp)
        return Response({"success": True})


class VerifyOTPView(APIView):
    def post(self, request):
        sp_id = request.data.get('sp_id')
        otp_code = request.data.get('otp_code')

        try:
            relation = StudentParent.objects.get(id=sp_id, otp_code=otp_code, status='pending_otp')

            if relation.otp_expires_at < timezone.now():
                return Response({"success": False, "message": "Kodning amal qilish muddati tugagan (3 daqiqa o'tdi)."}, status=status.HTTP_400_BAD_REQUEST)

            relation.status = 'verified'
            relation.otp_code = None 
            relation.save()

            return Response({
                "success": True, 
                "message": "Muvaffaqiyatli bog'landi!",
                "parent_tg_id": relation.parent.telegram_id,
                "student_name": relation.student.full_name
            }, status=status.HTTP_200_OK)

        except StudentParent.DoesNotExist:
            return Response({"success": False, "message": "Xato kod kiritildi yoki bunday bog'lanish yo'q."}, status=status.HTTP_404_NOT_FOUND)

class StudentProfileByTelegramIdView(APIView):
    def get(self, request, telegram_id):
        try:
            student = Student.objects.get(telegram_id=telegram_id)
            serializer = StudentProfileSerializer(student)
            return Response({"success": True, "student": serializer.data}, status=status.HTTP_200_OK)
        except Student.DoesNotExist:
            return Response({"success": False, "message": "Talaba tizimga kirmagan"}, status=status.HTTP_404_NOT_FOUND)


# --- SHU QISM O'ZGARTIRILDI (YANGI MODELGA MOSLANDI) ---
class ParentProfileByTelegramIdView(APIView):
    def get(self, request, telegram_id):
        try:
            parent = Parent.objects.get(telegram_id=telegram_id)
            serializer = ParentSerializer(parent)
            
            students_data = []
            for relation in parent.students.filter(status='verified'):
                student = relation.student
                payments_data = []
                # YANGILIK: Endi to'lovlarni oldin yozgan all_payments property'sidan oladi
                for p in student.all_payments: 
                    payments_data.append({
                        "amount": p.amount,
                        "academic_year": p.contract.academic_year, # Contractdan yilni oladi
                        "payment_date": p.payment_date.isoformat() if p.payment_date else None
                    })

                students_data.append({
                    "student_name": student.full_name,
                    "student_id": student.student_id,
                    "group_name": student.group.name if student.group else "Biriktirilmagan",
                    "total_contract_amount": student.total_contract_amount,
                    "paid_amount": student.paid_amount,
                    "debt_amount": student.debt_amount,
                    "status": relation.status,
                    "payments": payments_data
                })

            return Response({
                "success": True, 
                "parent": serializer.data,
                "linked_students": students_data
            }, status=status.HTTP_200_OK)
            
        except Parent.DoesNotExist:
            return Response({"success": False, "message": "Ota-ona topilmadi"}, status=status.HTTP_404_NOT_FOUND)

# --- QOLGAN FUNKSIYALAR TO'G'RI, SHUNDAY QOLDI ---
class ParentRegisterView(APIView):
    def post(self, request):
        data = request.data
        student_id = data.get('student_id')
        phone_number = data.get('phone_number')
        
        try:
            student = Student.objects.get(student_id=student_id)
            parent, created = Parent.objects.get_or_create(
                phone_number=phone_number,
                defaults={
                    'full_name': data.get('full_name'),
                    'telegram_id': data.get('telegram_id'),
                    'tg_username': data.get('tg_username'),
                    'tg_first_name': data.get('tg_first_name'),
                    'tg_last_name': data.get('tg_last_name'),
                }
            )

            if parent.is_blacklisted:
                return Response({"success": False, "message": "Bu raqam qora ro'yxatda!"}, status=403)

            otp = str(random.randint(100000, 999999))
            expires_at = timezone.now() + timedelta(minutes=3)

            sp_relation, sp_created = StudentParent.objects.update_or_create(
                student=student,
                parent=parent,
                defaults={
                    'role': data.get('role', 'other'),
                    'custom_role_name': data.get('custom_role_name', ''),
                    'status': 'pending_otp',
                    'otp_code': otp,
                    'otp_expires_at': expires_at
                }
            )
            return Response({"success": True, "otp_code": otp}, status=200)
        except Student.DoesNotExist:
            return Response({"success": False, "message": "Talaba topilmadi!"}, status=404)

class PendingParentsView(APIView):
    def get(self, request, student_id):
        pending_list = StudentParent.objects.filter(student__student_id=student_id, status='pending_otp')
        data = []
        for sp in pending_list:
            role_text = sp.get_role_display()
            if sp.role == 'other' and sp.custom_role_name:
                role_text = sp.custom_role_name
                
            data.append({
                "sp_id": sp.id,
                "phone": sp.parent.phone_number,
                "role_text": role_text,
                "tg_name": sp.parent.tg_first_name or "Noma'lum"
            })
        return Response({"success": True, "pending_list": data}, status=200)

class ResendOTPView(APIView):
    def post(self, request):
        sp_id = request.data.get('sp_id')
        sp = get_object_or_404(StudentParent, id=sp_id, status='pending_otp')
        
        new_otp = str(random.randint(100000, 999999))
        sp.otp_code = new_otp
        sp.otp_expires_at = timezone.now() + timedelta(minutes=3)
        sp.save()
        
        send_otp_to_telegram.delay(sp.parent.telegram_id, new_otp)
        return Response({"success": True, "message": "Yangi kod ota-onaga yuborildi!"})

class CancelPendingView(APIView):
    def post(self, request):
        sp_id = request.data.get('sp_id')
        StudentParent.objects.filter(id=sp_id, status='pending_otp').delete()
        return Response({"success": True})

class ParentInitRegisterView(APIView):
    def post(self, request):
        data = request.data
        try:
            student = Student.objects.get(student_id=data.get('student_id'))
            
            parent, created = Parent.objects.get_or_create(
                phone_number=data.get('phone_number'),
                defaults={
                    'full_name': data.get('full_name'),
                    'telegram_id': data.get('telegram_id'),
                    'tg_username': data.get('tg_username'),
                    'tg_first_name': data.get('tg_first_name'),
                }
            )

            if not created:
                parent.telegram_id = data.get('telegram_id')
                if not parent.full_name and data.get('full_name'):
                    parent.full_name = data.get('full_name')
                parent.save()

            if parent.is_blacklisted:
                return Response({"success": False, "message": "Bu raqam qora ro'yxatda!"})

            sp_relation, _ = StudentParent.objects.update_or_create(
                student=student,
                parent=parent,
                defaults={
                    'role': data.get('role', 'other'),
                    'custom_role_name': data.get('custom_role_name', ''),
                    'status': 'pending_otp',
                    'otp_code': None, 
                    'otp_expires_at': None
                }
            )

            role_display = sp_relation.custom_role_name if sp_relation.role == 'other' else sp_relation.get_role_display()

            return Response({
                "success": True, 
                "student_tg_id": student.telegram_id, 
                "sp_id": sp_relation.id,
                "role_display": role_display
            })
        except Student.DoesNotExist:
            return Response({"success": False, "message": "Talaba topilmadi"})