from django.contrib import admin
from .models import TutorPaymentConfirmation, ParentTutorVerification, NotificationFailure, PaymentSnapshot


@admin.register(PaymentSnapshot)
class PaymentSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'group', 'academic_year', 'tier_25', 'tier_50', 'tier_75', 'tier_100')
    list_filter = ('academic_year', 'snapshot_date', 'group')
    search_fields = ('group__name', 'academic_year')
    ordering = ('-snapshot_date',)
    list_per_page = 50

    actions = ['delete_selected']


@admin.register(TutorPaymentConfirmation)
class TutorPaymentConfirmationAdmin(admin.ModelAdmin):
    list_display = ('get_student', 'get_year', 'confirmed_by', 'confirmed_at', 'is_active', 'confirmed_amount')
    list_filter = ('is_active', 'confirmed_at')
    search_fields = ('contract__student__full_name', 'contract__student__student_id')
    ordering = ('-confirmed_at',)

    def get_student(self, obj):
        return obj.contract.student.full_name
    get_student.short_description = 'Talaba'

    def get_year(self, obj):
        return obj.contract.academic_year
    get_year.short_description = "O'quv yili"


@admin.register(ParentTutorVerification)
class ParentTutorVerificationAdmin(admin.ModelAdmin):
    list_display = ('student_parent', 'verified_by', 'verified_at')
    search_fields = ('student_parent__student__full_name',)
    ordering = ('-verified_at',)


@admin.register(NotificationFailure)
class NotificationFailureAdmin(admin.ModelAdmin):
    list_display = ('get_name', 'recipient_type', 'telegram_id', 'error_code', 'fail_count', 'last_failed_at')
    list_filter = ('recipient_type', 'error_code')
    search_fields = ('student__full_name', 'parent__phone_number', 'telegram_id')
    ordering = ('-last_failed_at',)

    def get_name(self, obj):
        if obj.student:
            return obj.student.full_name
        if obj.parent:
            return obj.parent.full_name or obj.parent.phone_number
        return '—'
    get_name.short_description = 'Kim'
