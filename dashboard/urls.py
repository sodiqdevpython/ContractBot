from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),

    # Guruhlar
    path('', views.GroupsView.as_view(), name='groups'),
    path('groups/<int:group_id>/', views.GroupDetailView.as_view(), name='group_detail'),

    # Talabalar
    path('students/<int:student_id>/', views.StudentDetailView.as_view(), name='student_detail'),
    path('students/<int:student_id>/confirm-payment/', views.ConfirmPaymentView.as_view(), name='confirm_payment'),
    path('students/<int:student_id>/cancel-confirmation/', views.CancelConfirmationView.as_view(), name='cancel_confirmation'),

    # Excel import
    path('excel-import/', views.ExcelImportView.as_view(), name='excel_import'),

    # Admin
    path('admin-overview/', views.AdminOverviewView.as_view(), name='admin_overview'),
]
