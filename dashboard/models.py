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
    note = models.TextField(blank=True, verbose_name="Izoh")

    class Meta:
        ordering = ['-confirmed_at']
        verbose_name = "Tutor to'lov tasdiqi"
        verbose_name_plural = "Tutor to'lov tasdiqlari"

    def __str__(self):
        status = "Faol" if self.is_active else "Bekor"
        return f"{self.contract.student.full_name} - {self.confirmed_at.date()} ({status})"
