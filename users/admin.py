from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from datetime import timedelta
from django import forms
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe
from django.contrib.auth.models import User
import openpyxl

from .models import Group, Student, StudentContract, Parent, StudentParent, Payment, NotificationCampaign, ExcelImport

# ==========================================
# 24 SOATLIK QULF UCHUN MAXSUS KLASS
# ==========================================
class LockableAdmin(admin.ModelAdmin):
    """
    Agar obyekt yaratilganiga 24 soatdan oshgan bo'lsa,
    tahrirlash va o'chirishni taqiqlaydi (Read-only qiladi).
    """
    def get_readonly_fields(self, request, obj=None):
        if obj and hasattr(obj, 'created_at') and obj.created_at:
            if timezone.now() > obj.created_at + timedelta(hours=24):
                return [f.name for f in self.model._meta.fields] # Barcha ustunlarni yopadi
        return super().get_readonly_fields(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and hasattr(obj, 'created_at') and obj.created_at:
            if timezone.now() > obj.created_at + timedelta(hours=24):
                return False # O'chirishni taqiqlaydi
        return super().has_delete_permission(request, obj)


# ==========================================
# GURUHLAR VA INLINE'LAR
# ==========================================
@admin.action(description="Tanlangan guruhlarning to'lov hisobini (0 ga) tushirish")
def reset_payments_for_groups(modeladmin, request, queryset):
    group_ids = list(queryset.values_list('id', flat=True))
    modeladmin.message_user(request, "Tanlangan guruhlar to'lovlarini 0 ga tushirish vazifasi orqa fonda ishga tushdi!")

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'tutor')
    list_filter = ('tutor',)
    search_fields = ('name', 'tutor__username', 'tutor__first_name', 'tutor__last_name')
    list_per_page = 20

class StudentParentInline(admin.TabularInline):
    model = StudentParent
    extra = 0
    readonly_fields = ('otp_code', 'otp_expires_at')

class StudentContractInline(admin.TabularInline):
    model = StudentContract
    extra = 0

class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


# ==========================================
# TALABALAR VA KONTRAKTLAR (24 soatlik qulf bilan)
# ==========================================
@admin.register(Student)
class StudentAdmin(LockableAdmin):
    list_display = ('student_id', 'full_name', 'group', 'tg_username', 'debt_amount', 'image_tag')
    list_filter = ('group',)
    search_fields = ('full_name', 'student_id', 'tg_username', 'telegram_id')
    inlines = [StudentParentInline, StudentContractInline]
    
    def image_tag(self, obj):
        if obj.profile_picture:
            return format_html('<img src="{}" style="width: 45px; height:45px; border-radius:50%;" />', obj.profile_picture.url)
        return "-"
    image_tag.short_description = 'Rasm'

    def debt_amount(self, obj):
        return obj.debt_amount
    debt_amount.short_description = "Qarzdorlik"

@admin.register(StudentContract)
class StudentContractAdmin(LockableAdmin):
    list_display = ('student', 'academic_year', 'course_level', 'is_grant', 'contract_amount', 'paid_amount', 'get_debt_amount')
    list_filter = ('academic_year', 'course_level', 'is_grant')
    search_fields = ('student__full_name', 'student__student_id')
    inlines = [PaymentInline]

    def get_debt_amount(self, obj):
        return obj.debt_amount
    get_debt_amount.short_description = "Qarzdorlik"


# ==========================================
# EXCEL IMPORT QILISH FORMASI VA VALIDATSIYASI
# ==========================================
class ExcelImportForm(forms.ModelForm):
    class Meta:
        model = ExcelImport
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Formada Namuna faylini yuklab olish uchun HTML link
        # self.fields['file'].help_text = mark_safe(
        #     "<br><a href='/media/namuna.xlsx' download style='color:#fff; background:#417690; padding:5px 10px; border-radius:4px; text-decoration:none; font-weight:bold;'>📥 Namuna shablonni yuklab olish</a>"
        #     "<br><br><i>Faqat .xlsx formatida va namunadagi kabi roppa-rosa '1, 2, 3, 4, 5, 6' raqamlangan ustunlardan iborat bo'lishi shart!</i>"
        # )

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            if not file.name.endswith('.xlsx'):
                raise ValidationError("Faqat .xlsx formatidagi Excel fayl yuklang!")
            try:
                # Faylni ochamiz va birinchi qatorni (Header) tekshiramiz
                wb = openpyxl.load_workbook(file, data_only=True)
                sheet = wb.active
                
                # A1 dan F1 gacha bo'lgan kataklardagi yozuvlarni olamiz
                headers = [str(sheet.cell(row=1, column=i).value).strip() for i in range(1, 7)]
                expected = ['1', '2', '3', '4', '5', '6']
                
                if headers != expected:
                    raise ValidationError(f"Shablon xato! 1-qator (A1 dan F1 gacha) {expected} bo'lishi kerak. Sizda esa: {headers}")
            except Exception as e:
                raise ValidationError(f"Faylni o'qishda xatolik yuz berdi: {str(e)}")
        return file

@admin.register(ExcelImport)
class ExcelImportAdmin(LockableAdmin):
    form = ExcelImportForm
    list_display = ('group', 'academic_year', 'created_at', 'file')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        
        # Fayl tizimga saqlangach, uni ochib talabalarni bazaga yozishni boshlaymiz
        try:
            wb = openpyxl.load_workbook(obj.file.path, data_only=True)
            sheet = wb.active
            
            created_count = 0
            # 2-qatordan boshlaymiz (chunki 1-qator bu [1, 2, 3, 4, 5, 6] degan Header)
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not row[0]: continue # Login ustuni bo'sh bo'lsa qatorni tashlab ketamiz
                
                # Ustunlardan kerakli ma'lumotlarni yig'amiz
                student_id = str(row[0]).strip()
                password = str(row[1]).strip()
                full_name = str(row[2]).strip()
                course = int(row[3]) if row[3] else 1
                contract_amt = float(row[4]) if row[4] else 0
                paid_amt = float(row[5]) if row[5] else 0
                
                # 1. Talabani yaratish yoki topish
                student, _ = Student.objects.update_or_create(
                    student_id=student_id,
                    defaults={
                        'password': password,
                        'full_name': full_name,
                        'group': obj.group
                    }
                )

                # 2. Django auth.User ni ham yaratish/yangilash (login uchun)
                django_user, _ = User.objects.get_or_create(
                    username=student_id,
                    defaults={'first_name': full_name}
                )
                django_user.set_password(password)
                django_user.first_name = full_name
                django_user.save()

                # 3. Ushbu o'quv yili uchun kontraktni yaratish yoki topish
                StudentContract.objects.update_or_create(
                    student=student,
                    academic_year=obj.academic_year,
                    defaults={
                        'course_level': course,
                        'contract_amount': contract_amt,
                        'paid_amount': paid_amt
                    }
                )
                created_count += 1
                
            self.message_user(request, f"Muvaffaqiyatli! {created_count} ta talaba bazaga qo'shildi/yangilandi.", level='SUCCESS')
        except Exception as e:
            self.message_user(request, f"Ma'lumotlarni bazaga yozishda xatolik: {str(e)}", level='ERROR')


# ==========================================
# QOLGAN BO'LIMLAR (Ota-onalar, To'lovlar, Bildirishnomalar)
# ==========================================
@admin.register(Parent)
class ParentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone_number', 'tg_first_name', 'tg_username', 'is_blacklisted', 'image_tag')
    list_filter = ('is_blacklisted', 'tg_language')
    search_fields = ('full_name', 'phone_number', 'tg_username', 'telegram_id')
    inlines = [StudentParentInline]

    def image_tag(self, obj):
        if obj.profile_picture:
            return format_html('<img src="{}" style="width: 45px; height:45px; border-radius:50%;" />', obj.profile_picture.url)
        return "-"
    image_tag.short_description = 'Rasm'

@admin.register(StudentParent)
class StudentParentAdmin(admin.ModelAdmin):
    list_display = ('student', 'parent', 'role', 'status')
    list_filter = ('status', 'role')
    search_fields = ('student__full_name', 'parent__phone_number')
    list_editable = ('status',)
    actions = ['mark_as_verified', 'mark_as_rejected']

    @admin.action(description="Tanlanganlarni 'Tasdiqlangan' deb belgilash")
    def mark_as_verified(self, request, queryset):
        queryset.update(status='verified')

    @admin.action(description="Tanlanganlarni 'Rad etish' va Qora ro'yxatga solish")
    def mark_as_rejected(self, request, queryset):
        queryset.update(status='rejected')
        for sp in queryset:
            sp.parent.is_blacklisted = True
            sp.parent.save()

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('get_student', 'get_academic_year', 'amount', 'payment_date')
    list_filter = ('contract__academic_year', 'payment_date')
    search_fields = ('contract__student__full_name', 'contract__student__student_id')

    def get_student(self, obj):
        return obj.contract.student.full_name
    get_student.short_description = 'Talaba'

    def get_academic_year(self, obj):
        return obj.contract.academic_year
    get_academic_year.short_description = "O'quv yili"

@admin.register(NotificationCampaign)
class NotificationCampaignAdmin(admin.ModelAdmin):
    list_display = ('id', 'student_type_filter', 'target_debt_tier', 'recipients', 'start_date', 'end_date', 'send_time')
    list_filter = ('student_type_filter', 'target_debt_tier', 'recipients')
    search_fields = ('message_text',)
    filter_horizontal = ('groups',)
    
    fieldsets = (
        ('Asosiy sozlamalar', {
            'fields': ('groups', 'student_type_filter', 'target_debt_tier', 'recipients')
        }),
        ('Xabar mazmuni', {
            'fields': ('message_text',)
        }),
        ('Vaqt va Muddatlar', {
            'fields': ('start_date', 'end_date', 'send_time')
        }),
    )