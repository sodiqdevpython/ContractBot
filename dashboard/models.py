from django.db import models
from django.contrib.auth.models import User


class TutorPaymentConfirmation(models.Model):
    """
    Tutor tomonidan talabaning to'lov qilganini tasdiqlash.
    Bu model faol bo'lsa, xabarnomalar to'xtatiladi.
    Excel import kelganda bu model o'chiriladi (Excel har doim haq).
    """
    contract = models.ForeignKey(
        'users.StudentContract',
        on_delete=models.CASCADE,
        related_name='tutor_confirmations',
        verbose_name="Shartnoma"
    )
    confirmed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='payment_confirmations',
        verbose_name="Tasdiqlagan tutor"
    )
    confirmed_at = models.DateTimeField(auto_now_add=True, verbose_name="Tasdiqlagan vaqti")
    is_active = models.BooleanField(default=True, verbose_name="Faolmi?")
    confirmed_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        verbose_name="Tasdiqlangan summa (so'm)"
    )
    note = models.TextField(blank=True, verbose_name="Izoh")

    class Meta:
        ordering = ['-confirmed_at']
        verbose_name = "Tutor to'lov tasdiqi"
        verbose_name_plural = "Tutor to'lov tasdiqlari"

    def __str__(self):
        status = "Faol" if self.is_active else "Bekor"
        return f"{self.contract.student.full_name} - {self.confirmed_at.date()} ({status})"


class ParentTutorVerification(models.Model):
    """
    Tutor tomonidan ota-onaning haqiqiyligini maksimal tierda tasdiqlash.
    Bu status — eng yuqori ishonch tiersi: tutor shaxsan ko'rgan yoki gaplashgan.
    OTP orqali 'verified' bo'lish — oddiy tier.
    Bu model — maksimal tier.
    """
    student_parent = models.OneToOneField(
        'users.StudentParent',
        on_delete=models.CASCADE,
        related_name='tutor_verification',
        verbose_name="Talaba–Ota-ona"
    )
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='parent_verifications',
        verbose_name="Tasdiqlagan tutor"
    )
    verified_at = models.DateTimeField(auto_now_add=True, verbose_name="Tasdiqlagan vaqti")
    note = models.TextField(blank=True, verbose_name="Izoh")

    class Meta:
        verbose_name = "Tutor ota-ona tasdiqi"
        verbose_name_plural = "Tutor ota-ona tasdiqlari"

    def __str__(self):
        return f"{self.student_parent} — Tutor tasdiqladi"


class NotificationFailure(models.Model):
    """
    Telegramdan xabar yetib bormagan talaba yoki ota-onalar.
    Faqat muvaffaqiyatsiz xabarlar saqlanadi.
    Agar keyingi xabar muvaffaqiyatli bo'lsa — bu yozuv o'chiriladi.
    Sabab: bot bloklangan, account o'chirilgan va h.k.
    """
    RECIPIENT_STUDENT = 'student'
    RECIPIENT_PARENT  = 'parent'
    RECIPIENT_CHOICES = [
        (RECIPIENT_STUDENT, 'Talaba'),
        (RECIPIENT_PARENT,  'Ota-ona'),
    ]

    student = models.ForeignKey(
        'users.Student',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notification_failures',
        verbose_name="Talaba"
    )
    parent = models.ForeignKey(
        'users.Parent',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notification_failures',
        verbose_name="Ota-ona"
    )
    telegram_id = models.BigIntegerField(verbose_name="Telegram ID")
    recipient_type = models.CharField(
        max_length=10, choices=RECIPIENT_CHOICES, verbose_name="Kim"
    )
    error_code = models.IntegerField(null=True, blank=True, verbose_name="Xato kodi")
    error_description = models.TextField(verbose_name="Xato tavsifi")
    fail_count = models.PositiveIntegerField(default=1, verbose_name="Xato soni")
    last_failed_at = models.DateTimeField(auto_now=True, verbose_name="Oxirgi xato vaqti")
    is_otp = models.BooleanField(default=False, verbose_name="OTP yuborishda xatomi?")
    campaign = models.ForeignKey(
        'users.NotificationCampaign',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Kampaniya"
    )

    class Meta:
        # Har bir foydalanuvchi uchun bitta yozuv
        unique_together = [('telegram_id', 'recipient_type')]
        ordering = ['-last_failed_at']
        verbose_name = "Xabarnoma xatosi"
        verbose_name_plural = "Xabarnoma xatolari"

    def __str__(self):
        name = self.student.full_name if self.student else (
            self.parent.full_name or self.parent.phone_number if self.parent else "?"
        )
        return f"{name} — xato {self.error_code} ({self.last_failed_at.date()})"


class PaymentSnapshot(models.Model):
    """
    Har bir Excel import qilinganda saqlanadigan to'lov holati surati.
    Har guruh uchun alohida yozuv. Exclusive tier logikasi:
      - tier_25  : ≥25% < 50% to'lagan talabalar soni
      - tier_50  : ≥50% < 75% to'lagan talabalar soni
      - tier_75  : ≥75% < 100% to'lagan talabalar soni
      - tier_100 : 100% to'lagan talabalar soni
    Har talaba faqat BITTA tierga kiradi.
    """
    snapshot_date = models.DateField(auto_now_add=True, verbose_name="Sana")
    academic_year  = models.CharField(max_length=9, verbose_name="O'quv yili")
    group = models.ForeignKey(
        'users.Group',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='payment_snapshots',
        verbose_name="Guruh"
    )
    tier_25  = models.PositiveIntegerField(default=0, verbose_name="25% to'lovchilar")
    tier_50  = models.PositiveIntegerField(default=0, verbose_name="50% to'lovchilar")
    tier_75  = models.PositiveIntegerField(default=0, verbose_name="75% to'lovchilar")
    tier_100 = models.PositiveIntegerField(default=0, verbose_name="100% to'lovchilar")

    class Meta:
        ordering = ['-snapshot_date', 'group__name']
        verbose_name = "To'lov surati"
        verbose_name_plural = "To'lov suratlari"

    def __str__(self):
        g = self.group.name if self.group else "Barchasi"
        return f"{self.snapshot_date} — {g}"
