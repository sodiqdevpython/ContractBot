from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, Count, Q

from users.models import Group, Student, StudentContract, Payment, current_academic_year
from .models import TutorPaymentConfirmation
from .excel_parser import parse_multi_group_excel
from .forms import LoginForm, ExcelImportForm, ConfirmPaymentForm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_accessible_groups(user):
    """Foydalanuvchiga ruxsat berilgan guruhlarni qaytaradi."""
    if user.is_staff:
        return Group.objects.all().select_related('tutor')
    return Group.objects.filter(tutor=user).select_related('tutor')


def can_access_student(user, student):
    """Tutor faqat o'z guruhidagi talabalarga kira oladi."""
    if user.is_staff:
        return True
    if student.group is None:
        return False
    return student.group.tutor_id == user.pk


def group_stats(group, academic_year):
    students = Student.objects.filter(group=group)
    contracts = StudentContract.objects.filter(
        student__in=students, academic_year=academic_year
    )
    agg = contracts.aggregate(
        total_contract=Sum('contract_amount'),
        total_paid=Sum('paid_amount'),
    )
    total_contract = agg['total_contract'] or 0
    total_paid = agg['total_paid'] or 0
    return {
        'student_count': students.count(),
        'contract_count': contracts.count(),
        'total_contract': total_contract,
        'total_paid': total_paid,
        'total_debt': total_contract - total_paid,
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('dashboard:groups')
        return render(request, 'dashboard/login.html', {'form': LoginForm()})

    def post(self, request):
        form = LoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect(request.GET.get('next', 'dashboard:groups'))
        return render(request, 'dashboard/login.html', {'form': form})


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect('dashboard:login')


# ---------------------------------------------------------------------------
# Groups list
# ---------------------------------------------------------------------------

@method_decorator(login_required(login_url='/dashboard/login/'), name='dispatch')
class GroupsView(View):
    def get(self, request):
        current_year = current_academic_year()
        groups = get_accessible_groups(request.user)

        groups_data = []
        totals = {'students': 0, 'debt': 0, 'contract': 0}

        for group in groups:
            stats = group_stats(group, current_year)
            groups_data.append({'group': group, **stats})
            totals['students'] += stats['student_count']
            totals['debt'] += stats['total_debt']
            totals['contract'] += stats['total_contract']

        # Qarzga ko'ra tartiblash (ko'pdan kamga)
        groups_data.sort(key=lambda x: x['total_debt'], reverse=True)

        context = {
            'groups_data': groups_data,
            'current_year': current_year,
            'totals': totals,
        }
        return render(request, 'dashboard/groups.html', context)


# ---------------------------------------------------------------------------
# Group detail
# ---------------------------------------------------------------------------

@method_decorator(login_required(login_url='/dashboard/login/'), name='dispatch')
class GroupDetailView(View):
    def get(self, request, group_id):
        group = get_object_or_404(Group, pk=group_id)

        if not request.user.is_staff and group.tutor_id != request.user.pk:
            messages.error(request, "Sizda bu guruhga kirish huquqi yo'q.")
            return redirect('dashboard:groups')

        current_year = current_academic_year()
        search = request.GET.get('q', '').strip()
        debt_filter = request.GET.get('debt', '')  # 'has_debt' | 'no_debt' | ''

        students_qs = Student.objects.filter(group=group).prefetch_related('contracts')

        if search:
            students_qs = students_qs.filter(
                Q(full_name__icontains=search) | Q(student_id__icontains=search)
            )

        students_data = []
        for student in students_qs:
            contract = student.contracts.filter(academic_year=current_year).first()
            debt = float(contract.debt_amount) if contract else 0
            contract_amount = float(contract.contract_amount) if contract else 0
            paid_amount = float(contract.paid_amount) if contract else 0

            # Tutor tasdiqlash holati
            has_confirmation = False
            if contract:
                has_confirmation = contract.tutor_confirmations.filter(is_active=True).exists()

            students_data.append({
                'student': student,
                'contract': contract,
                'debt': debt,
                'contract_amount': contract_amount,
                'paid_amount': paid_amount,
                'has_confirmation': has_confirmation,
                'debt_pct': round((paid_amount / contract_amount * 100) if contract_amount > 0 else 100),
            })

        # Filtr
        if debt_filter == 'has_debt':
            students_data = [s for s in students_data if s['debt'] > 0]
        elif debt_filter == 'no_debt':
            students_data = [s for s in students_data if s['debt'] <= 0]

        # Qarzga ko'ra tartiblash
        students_data.sort(key=lambda x: x['debt'], reverse=True)

        stats = group_stats(group, current_year)

        context = {
            'group': group,
            'students_data': students_data,
            'current_year': current_year,
            'search': search,
            'debt_filter': debt_filter,
            'stats': stats,
        }
        return render(request, 'dashboard/group_detail.html', context)


# ---------------------------------------------------------------------------
# Student detail
# ---------------------------------------------------------------------------

@method_decorator(login_required(login_url='/dashboard/login/'), name='dispatch')
class StudentDetailView(View):
    def get(self, request, student_id):
        student = get_object_or_404(Student, pk=student_id)

        if not can_access_student(request.user, student):
            messages.error(request, "Sizda bu talabaga kirish huquqi yo'q.")
            return redirect('dashboard:groups')

        current_year = current_academic_year()
        current_contract = student.contracts.filter(academic_year=current_year).first()

        active_confirmation = None
        if current_contract:
            active_confirmation = current_contract.tutor_confirmations.filter(
                is_active=True
            ).first()

        all_contracts = student.contracts.order_by('-academic_year')
        all_payments = student.all_payments

        confirm_form = ConfirmPaymentForm()

        context = {
            'student': student,
            'current_year': current_year,
            'current_contract': current_contract,
            'active_confirmation': active_confirmation,
            'all_contracts': all_contracts,
            'all_payments': all_payments,
            'confirm_form': confirm_form,
        }
        return render(request, 'dashboard/student_detail.html', context)


# ---------------------------------------------------------------------------
# Confirm payment
# ---------------------------------------------------------------------------

@method_decorator(login_required(login_url='/dashboard/login/'), name='dispatch')
class ConfirmPaymentView(View):
    def post(self, request, student_id):
        student = get_object_or_404(Student, pk=student_id)

        if not can_access_student(request.user, student):
            messages.error(request, "Sizda bu talabaga kirish huquqi yo'q.")
            return redirect('dashboard:groups')

        current_year = current_academic_year()
        contract = student.contracts.filter(academic_year=current_year).first()

        if not contract:
            messages.error(request, "Joriy yil uchun shartnoma topilmadi.")
            return redirect('dashboard:student_detail', student_id=student_id)

        # Avvalgi faol tasdiqqlarni o'chiramiz
        TutorPaymentConfirmation.objects.filter(
            contract=contract, is_active=True
        ).update(is_active=False)

        note = request.POST.get('note', '').strip()
        TutorPaymentConfirmation.objects.create(
            contract=contract,
            confirmed_by=request.user,
            is_active=True,
            note=note,
        )

        messages.success(
            request,
            f"{student.full_name} uchun to'lov tasdiqlandi. Xabarnomalar to'xtatildi."
        )
        return redirect('dashboard:student_detail', student_id=student_id)


class CancelConfirmationView(View):
    @method_decorator(login_required(login_url='/dashboard/login/'))
    def post(self, request, student_id):
        student = get_object_or_404(Student, pk=student_id)

        if not can_access_student(request.user, student):
            messages.error(request, "Sizda bu talabaga kirish huquqi yo'q.")
            return redirect('dashboard:groups')

        current_year = current_academic_year()
        contract = student.contracts.filter(academic_year=current_year).first()

        if contract:
            TutorPaymentConfirmation.objects.filter(
                contract=contract, is_active=True
            ).update(is_active=False)
            messages.info(request, "Tasdiqlash bekor qilindi. Xabarnomalar qayta faollashadi.")

        return redirect('dashboard:student_detail', student_id=student_id)


# ---------------------------------------------------------------------------
# Excel import
# ---------------------------------------------------------------------------

@method_decorator(login_required(login_url='/dashboard/login/'), name='dispatch')
class ExcelImportView(View):
    def get(self, request):
        form = ExcelImportForm(initial={'academic_year': current_academic_year()})
        return render(request, 'dashboard/excel_import.html', {'form': form})

    def post(self, request):
        form = ExcelImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, 'dashboard/excel_import.html', {'form': form})

        excel_file = request.FILES['file']
        academic_year = form.cleaned_data['academic_year']

        try:
            sections = parse_multi_group_excel(excel_file)
        except Exception as e:
            messages.error(request, f"Faylni o'qishda xatolik: {e}")
            return render(request, 'dashboard/excel_import.html', {'form': form})

        if not sections:
            messages.error(request, "Fayl bo'sh yoki guruh topilmadi. Formatni tekshiring.")
            return render(request, 'dashboard/excel_import.html', {'form': form})

        # Foydalanuvchiga ruxsat berilgan guruhlar
        if request.user.is_staff:
            accessible = {g.name.lower(): g for g in Group.objects.all()}
        else:
            accessible = {g.name.lower(): g for g in Group.objects.filter(tutor=request.user)}

        results = []
        errors = []

        for group_name, students_data in sections.items():
            if group_name not in accessible:
                if Group.objects.filter(name__iexact=group_name).exists():
                    errors.append(
                        f"'{group_name}' guruhi tizimda mavjud, lekin siz unga biriktirilmagan."
                    )
                else:
                    errors.append(
                        f"'{group_name}' guruhi tizimda yo'q. Bu bo'lim o'tkazib yuborildi."
                    )
                continue

            group = accessible[group_name]
            created_count = 0
            updated_count = 0
            row_errors = []

            for student_data in students_data:
                try:
                    with transaction.atomic():
                        student, student_created = Student.objects.get_or_create(
                            student_id=student_data['student_id'],
                            defaults={
                                'full_name': student_data['full_name'],
                                'password': student_data['password'],
                                'group': group,
                            }
                        )

                        if not student_created:
                            student.full_name = student_data['full_name']
                            student.password = student_data['password']
                            student.group = group
                            student.save(update_fields=['full_name', 'password', 'group'])

                        contract, contract_created = StudentContract.objects.get_or_create(
                            student=student,
                            academic_year=academic_year,
                            defaults={
                                'course_level': student_data['course_level'],
                                'contract_amount': student_data['contract_amount'],
                                'paid_amount': student_data['paid_amount'],
                                'is_grant': student_data['contract_amount'] == 0,
                            }
                        )

                        if not contract_created:
                            # Excel har doim haq - yangilash
                            contract.course_level = student_data['course_level']
                            contract.contract_amount = student_data['contract_amount']
                            contract.paid_amount = student_data['paid_amount']
                            contract.is_grant = student_data['contract_amount'] == 0
                            contract.save(update_fields=[
                                'course_level', 'contract_amount', 'paid_amount', 'is_grant'
                            ])

                            # Excel yangilandi — tutor tasdiqqlarini bekor qilamiz
                            TutorPaymentConfirmation.objects.filter(
                                contract=contract, is_active=True
                            ).update(is_active=False)

                        if student_created:
                            created_count += 1
                        else:
                            updated_count += 1

                except Exception as e:
                    row_errors.append(f"ID {student_data.get('student_id', '?')}: {e}")

            results.append({
                'group': group_name,
                'created': created_count,
                'updated': updated_count,
                'total': len(students_data),
                'row_errors': row_errors,
            })
            errors.extend(row_errors)

        context = {
            'form': ExcelImportForm(initial={'academic_year': academic_year}),
            'results': results,
            'errors': errors,
            'imported': True,
        }
        return render(request, 'dashboard/excel_import.html', context)


# ---------------------------------------------------------------------------
# Admin overview
# ---------------------------------------------------------------------------

@method_decorator(login_required(login_url='/dashboard/login/'), name='dispatch')
class AdminOverviewView(View):
    def get(self, request):
        if not request.user.is_staff:
            messages.error(request, "Bu sahifaga faqat adminlar kira oladi.")
            return redirect('dashboard:groups')

        current_year = current_academic_year()
        all_groups = Group.objects.select_related('tutor').all()

        groups_data = []
        for group in all_groups:
            stats = group_stats(group, current_year)
            groups_data.append({'group': group, **stats})

        groups_data.sort(key=lambda x: x['total_debt'], reverse=True)

        total_students = Student.objects.count()
        total_contracts = StudentContract.objects.filter(academic_year=current_year).count()
        agg = StudentContract.objects.filter(academic_year=current_year).aggregate(
            total_contract=Sum('contract_amount'),
            total_paid=Sum('paid_amount'),
        )
        total_contract = agg['total_contract'] or 0
        total_paid = agg['total_paid'] or 0
        total_debt = total_contract - total_paid

        # Eng ko'p qarzli 10 ta talaba
        top_debtors = []
        for contract in StudentContract.objects.filter(
            academic_year=current_year
        ).select_related('student', 'student__group').order_by('-contract_amount'):
            debt = float(contract.debt_amount)
            if debt > 0:
                top_debtors.append({'student': contract.student, 'contract': contract, 'debt': debt})
            if len(top_debtors) >= 10:
                break

        context = {
            'groups_data': groups_data,
            'current_year': current_year,
            'total_students': total_students,
            'total_contracts': total_contracts,
            'total_contract': total_contract,
            'total_paid': total_paid,
            'total_debt': total_debt,
            'top_debtors': top_debtors,
            'groups_count': all_groups.count(),
        }
        return render(request, 'dashboard/admin_overview.html', context)
