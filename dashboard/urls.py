from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('login/',  views.LoginView.as_view(),  name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),

    # Guruhlar
    path('',                          views.GroupsView.as_view(),      name='groups'),
    path('groups/<int:group_id>/',    views.GroupDetailView.as_view(), name='group_detail'),

    # Talabalar
    path('students/<int:student_id>/',                    views.StudentDetailView.as_view(),   name='student_detail'),
    path('students/<int:student_id>/confirm-payment/',    views.ConfirmPaymentView.as_view(),  name='confirm_payment'),
    path('students/<int:student_id>/cancel-confirmation/',views.CancelConfirmationView.as_view(), name='cancel_confirmation'),

    # Ota-onalar
    path('parents/',                          views.ParentsView.as_view(),    name='parents'),
    path('parents/verify/<int:sp_id>/',       views.VerifyParentView.as_view(),   name='verify_parent'),
    path('parents/unverify/<int:sp_id>/',     views.UnverifyParentView.as_view(), name='unverify_parent'),

    # Xabarnoma xatolari
    path('notification-failures/', views.NotificationFailuresView.as_view(), name='notification_failures'),

    # Xabarnoma yuborish (bulk campaign)
    path('campaigns/send/',     views.CampaignSendView.as_view(),     name='campaign_send'),
    path('campaigns/schedule/', views.CampaignScheduleView.as_view(), name='campaign_schedule'),

    # To'lov statistikasi
    path('payment-stats/', views.PaymentStatsView.as_view(), name='payment_stats'),

    # Excel import
    path('excel-import/', views.ExcelImportView.as_view(), name='excel_import'),

    # Excel shablon yuklab olish
    path('excel-template/', views.ExcelTemplateView.as_view(), name='excel_template'),

    # Admin
    path('admin-overview/', views.AdminOverviewView.as_view(), name='admin_overview'),
]
