from django.urls import path
from .views import (
    StudentLoginView, 
    ParentRegisterView, 
    VerifyOTPView, 
    StudentProfileByTelegramIdView,
    ParentProfileByTelegramIdView,
    PendingParentsView,
    ResendOTPView,
    CancelPendingView, ParentInitRegisterView, TriggerOTPView
)

urlpatterns = [
    path('api/student/login/', StudentLoginView.as_view(), name='student-login'),
    path('api/student/profile/<int:telegram_id>/', StudentProfileByTelegramIdView.as_view(), name='student-profile'),
    
    path('api/parent/register/', ParentRegisterView.as_view(), name='parent-register'),
    path('api/parent/verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('api/parent/profile/<int:telegram_id>/', ParentProfileByTelegramIdView.as_view(), name='parent-profile'),

    path('api/parent/pending/<str:student_id>/', PendingParentsView.as_view(), name='pending_parents'),
    path('api/parent/resend-otp/', ResendOTPView.as_view(), name='resend_otp'),
    path('api/parent/cancel-pending/', CancelPendingView.as_view(), name='cancel_pending'),

    path('api/parent/init-register/', ParentInitRegisterView.as_view()),
    path('api/parent/trigger-otp/', TriggerOTPView.as_view()),
]