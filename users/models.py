from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db.models import Sum

def current_academic_year():
    now = timezone.now()
    year = now.year
    if now.month < 8:
        return f"{year-1}-{year}"
    return f"{year}-{year+1}"

class Group(models.Model):
    name = models.CharField(max_length=255, verbose_name="Guruh nomi")
    tutor = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='tutored_groups',
        verbose_name="Tyutor"
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Guruh"
        verbose_name_plural = "Guruhlar"

class Student(models.Model):
    student_id = models.CharField(max_length=20, unique=True, verbose_name="Talaba ID (Login)")
    password = models.CharField(max_length=128, verbose_name="Parol")
    full_name = models.CharField(max_length=150, verbose_name="F.I.SH (O'qishdagi)")
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, verbose_name="Guruhi")
    
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True, verbose_name="Telegram ID")
    tg_username = models.CharField(max_length=100, null=True, blank=True, verbose_name="TG Username")
    tg_first_name = models.CharField(max_length=150, null=True, blank=True, verbose_name="TG Ismi")
    tg_last_name = models.CharField(max_length=150, null=True, blank=True, verbose_name="TG Familiyasi")
    tg_language = models.CharField(max_length=10, null=True, blank=True, verbose_name="Dastur tili")
    profile_picture = models.ImageField(upload_to='students_profiles/', null=True, blank=True, verbose_name="Profil rasmi")

    created_at = models.DateTimeField(auto_now_add=True, null=True, verbose_name="Yaratilgan vaqti")

    # API VA BOT BUZILMASLIGI UCHUN DYNAMIC PROPERTY'LAR
    @property
    def total_contract_amount(self):
        # Barcha yillardagi kontraktlar yig'indisi
        total = self.contracts.aggregate(Sum('contract_amount'))['contract_amount__sum']
        return total or 0

    @property
    def paid_amount(self):
        # Barcha yillardagi to'lovlar yig'indisi
        total = self.contracts.aggregate(Sum('paid_amount'))['paid_amount__sum']
        return total or 0

    @property
    def debt_amount(self):
        return self.total_contract_amount - self.paid_amount

    @property
    def all_payments(self):
        # Talabaning barcha shartnomalari bo'yicha qilingan to'lovlarini yig'ib beradi
        return Payment.objects.filter(contract__student=self).order_by('-payment_date')

    def __str__(self):
        return f"{self.full_name} ({self.student_id})"

    class Meta:
        verbose_name = "Talaba"
        verbose_name_plural = "Talabalar"

class StudentContract(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='contracts', verbose_name="Talaba")
    academic_year = models.CharField(max_length=9, verbose_name="O'quv yili (Masalan: 2023-2024)")
    course_level = models.PositiveSmallIntegerField(verbose_name="Kursi (1, 2, 3, 4)", default=1)
    
    is_grant = models.BooleanField(default=False, verbose_name="Grant asosidami?")
    contract_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Shu yilgi kontrakt summasi")
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Shu yil uchun to'langan summa")

    created_at = models.DateTimeField(auto_now_add=True, null=True, verbose_name="Yaratilgan vaqti")

    @property
    def debt_amount(self):
        return self.contract_amount - self.paid_amount

    def __str__(self):
        return f"{self.student.full_name} - {self.academic_year} ({self.course_level}-kurs)"

    class Meta:
        verbose_name = "Talaba kontrakti"
        verbose_name_plural = "Talabalar kontraktlari"
        unique_together = ('student', 'academic_year')

class Parent(models.Model):
    phone_number = models.CharField(max_length=20, unique=True, verbose_name="Telefon raqami")
    full_name = models.CharField(max_length=150, null=True, blank=True, verbose_name="F.I.SH")
    
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True, verbose_name="Telegram ID")
    tg_username = models.CharField(max_length=100, null=True, blank=True, verbose_name="TG Username")
    tg_first_name = models.CharField(max_length=150, null=True, blank=True, verbose_name="TG Ismi")
    tg_last_name = models.CharField(max_length=150, null=True, blank=True, verbose_name="TG Familiyasi")
    tg_language = models.CharField(max_length=10, null=True, blank=True, verbose_name="Dastur tili")
    profile_picture = models.ImageField(upload_to='parents_profiles/', null=True, blank=True, verbose_name="Profil rasmi")
    
    is_blacklisted = models.BooleanField(default=False, verbose_name="Qora ro'yxatdami?")

    def __str__(self):
        return f"{self.tg_first_name} - {self.phone_number}"

    class Meta:
        verbose_name = "Ota-ona"
        verbose_name_plural = "Ota-onalar"

class StudentParent(models.Model):
    STATUS_CHOICES = (
        ('pending_otp', 'OTP kutilmoqda'),
        ('pending_admin', 'Admin tasdiqlagan'),
        ('verified', 'Tasdiqlangan'),
        ('rejected', 'Rad etilgan (Qora ro\'yxat)'),
    )
    ROLE_CHOICES = (
        ('father', 'Ota'),
        ('mother', 'Ona'),
        ('other', 'Boshqa (Aka/Opa)'),
    )

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='parents', verbose_name="Talaba")
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE, related_name='students', verbose_name="Ota-ona")
    role = models.CharField(max_length=150, choices=ROLE_CHOICES, verbose_name="Qarindoshlik darajasi", null=True, blank=True)

    custom_role_name = models.CharField(max_length=100, null=True, blank=True, verbose_name="Kimligi (Boshqa)")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_otp', verbose_name="Status")
    otp_code = models.CharField(max_length=6, null=True, blank=True, verbose_name="OTP Kod")
    otp_expires_at = models.DateTimeField(null=True, blank=True, verbose_name="OTP muddati")

    class Meta:
        unique_together = ('student', 'parent')
        verbose_name = "Talaba va Ota-ona bog'lanishi"
        verbose_name_plural = "Talaba va Ota-onalar"

    def clean(self):
        if self.pk is None:
            existing_kids_count = StudentParent.objects.filter(parent=self.parent).count()
            if existing_kids_count >= 3:
                raise ValidationError("Limit tugadi: Bitta raqamga eng ko'pi 3 ta talaba ulanishi mumkin!")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.full_name} -> {self.parent.phone_number} ({self.get_status_display()})"

class Payment(models.Model):
    contract = models.ForeignKey(StudentContract, on_delete=models.CASCADE, related_name='payments', verbose_name="Shartnoma")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="To'lov summasi")
    payment_date = models.DateField(default=timezone.now, verbose_name="To'lov sanasi")

    def save(self, *args, **kwargs):
        is_new = self.pk is None 
        super().save(*args, **kwargs)
        
        # Yangi to'lov faqat tegishli contract ning to'langan summasini oshiradi
        if is_new:
            self.contract.paid_amount += self.amount
            self.contract.save()

    def __str__(self):
        return f"{self.contract.student.full_name} - {self.amount} so'm ({self.contract.academic_year})"

    class Meta:
        verbose_name = "To'lov"
        verbose_name_plural = "To'lovlar"

class NotificationCampaign(models.Model):
    TIER_CHOICES = (
        (0, 'Qarzdan qat\'i nazar (E\'lonlar uchun)'),
        (25, '25% (1-chorak) to\'lamaganlar uchun'),
        (50, '50% (Yarim yillik) to\'lamaganlar uchun'),
        (75, '75% (3-chorak) to\'lamaganlar uchun'),
        (100, '100% (To\'liq) to\'lamaganlar uchun'),
    )
    RECIPIENT_CHOICES = (
        ('student_only', 'Faqat talabalarning o\'ziga'),
        ('student_and_parent', 'Talaba va ularning Ota-onalariga'),
        ('parent_only', 'Faqat Ota-onalarga'),
    )
    STUDENT_TYPE_CHOICES = (
        ('contract_only', 'Faqat kontrakt asosida o\'qiydiganlarga'),
        ('grant_only', 'Faqat grant asosida o\'qiydiganlarga'),
        ('all', 'Barchaga (Grant + Kontrakt)'),
    )
    
    groups = models.ManyToManyField(Group, related_name='campaigns', verbose_name="Qaysi guruhlarga?")
    student_type_filter = models.CharField(max_length=20, choices=STUDENT_TYPE_CHOICES, default='contract_only', verbose_name="Kimlarga (Grant/Kontrakt)")
    target_debt_tier = models.PositiveSmallIntegerField(choices=TIER_CHOICES, verbose_name="Qarz chegarasi (Filtr)")
    recipients = models.CharField(max_length=30, choices=RECIPIENT_CHOICES, default='student_only', verbose_name="Kimlarga yuborilsin?")
    message_text = models.TextField(verbose_name="Yuboriladigan xabar matni")
    
    start_date = models.DateField(verbose_name="Boshlanish sanasi")
    end_date = models.DateField(verbose_name="Tugash sanasi")
    send_time = models.TimeField(verbose_name="Kunlik yuborish vaqti")

    def __str__(self):
        return f"Xabarnoma ({self.start_date} - {self.end_date})"

    class Meta:
        verbose_name = "Xabarnoma"
        verbose_name_plural = "Xabarnomalar"




class ExcelImport(models.Model):
    group = models.ForeignKey('Group', on_delete=models.CASCADE, verbose_name="Guruhni tanlang")
    academic_year = models.CharField(max_length=9, default=current_academic_year, verbose_name="O'quv yili")
    file = models.FileField(upload_to='excel_imports/', verbose_name="Excel faylni yuklang")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Kiritilgan vaqti")

    class Meta:
        verbose_name = "Hisobot (Excel) kiritish"
        verbose_name_plural = "Hisobotlar (Excel) kiritish"

    def __str__(self):
        return f"{self.group.name} - {self.academic_year}"

