import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.core.paginator import Paginator
from django.http import HttpResponse

from users.models import Group, Student, StudentContract, Payment, StudentParent, Parent, current_academic_year
from .models import TutorPaymentConfirmation, ParentTutorVerification, NotificationFailure, PaymentSnapshot
from .excel_parser import parse_multi_group_excel
from .forms import LoginForm, ExcelImportForm, ConfirmPaymentForm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_accessible_groups(user):
    if user.is_staff:
        return Group.objects.all().select_related('tutor')
    return Group.objects.filter(tutor=user).select_related('tutor')


def can_access_student(user, student):
    if user.is_staff:
        return True
    if student.group is None:
        return False
    return student.group.tutor_id == user.pk


def group_stats(group, academic_year):
    students = Student.objects.filter(group=group)
    contracts = StudentContract.objects.filter(student__in=students, academic_year=academic_year)
    agg = contracts.aggregate(total_contract=Sum('contract_amount'), total_paid=Sum('paid_amount'))
    total_contract = agg['total_contract'] or 0
    total_paid = agg['total_paid'] or 0
    return {
        'student_count': students.count(),
        'contract_count': contracts.count(),
        'total_contract': total_contract,
        'total_paid': total_paid,
        'total_debt': total_contract - total_paid,
    }


def _calc_pct(contract):
    """To'lov foizini qaytaradi (0.0–100.0+)."""
    if not contract or contract.contract_amount == 0:
        return 100.0
    return float(contract.paid_amount) / float(contract.contract_amount) * 100.0


def _calc_tier(pct):
    """Exclusive tier: 0, 25, 50, 75 yoki 100."""
    if pct >= 100: return 100
    if pct >= 75:  return 75
    if pct >= 50:  return 50
    if pct >= 25:  return 25
    return 0


def _take_snapshot(group, academic_year):
    """Excel import qilinganda guruh bo'yicha to'lov suratini yangilaydi."""
    from django.utils import timezone
    contracts = StudentContract.objects.filter(
        student__group=group, academic_year=academic_year
    )
    t = {25: 0, 50: 0, 75: 0, 100: 0}
    for c in contracts:
        tier = _calc_tier(_calc_pct(c))
        if tier in t:
            t[tier] += 1

    PaymentSnapshot.objects.update_or_create(
        snapshot_date=timezone.localdate(),
        group=group,
        academic_year=academic_year,
        defaults={
            'tier_25': t[25], 'tier_50': t[50],
            'tier_75': t[75], 'tier_100': t[100],
        }
    )


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
        debt_filter = request.GET.get('debt', '')

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

        if debt_filter == 'has_debt':
            students_data = [s for s in students_data if s['debt'] > 0]
        elif debt_filter == 'no_debt':
            students_data = [s for s in students_data if s['debt'] <= 0]

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
            active_confirmation = current_contract.tutor_confirmations.filter(is_active=True).first()

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
# Confirm / Cancel payment
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

        TutorPaymentConfirmation.objects.filter(contract=contract, is_active=True).update(is_active=False)
        note = request.POST.get('note', '').strip()
        TutorPaymentConfirmation.objects.create(
            contract=contract, confirmed_by=request.user, is_active=True, note=note,
        )
        messages.success(request, f"{student.full_name} uchun to'lov tasdiqlandi. Xabarnomalar to'xtatildi.")
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
            TutorPaymentConfirmation.objects.filter(contract=contract, is_active=True).update(is_active=False)
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

        if request.user.is_staff:
            accessible = {g.name.lower(): g for g in Group.objects.all()}
        else:
            accessible = {g.name.lower(): g for g in Group.objects.filter(tutor=request.user)}

        results = []
        errors = []

        for group_name, students_data in sections.items():
            if group_name not in accessible:
                if Group.objects.filter(name__iexact=group_name).exists():
                    errors.append(f"'{group_name}' guruhi tizimda mavjud, lekin siz unga biriktirilmagan.")
                else:
                    errors.append(f"'{group_name}' guruhi tizimda yo'q. Bu bo'lim o'tkazib yuborildi.")
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

                        # Django auth.User ni ham yaratish/yangilash
                        django_user, _ = User.objects.get_or_create(
                            username=student_data['student_id'],
                            defaults={'first_name': student_data['full_name']}
                        )
                        django_user.set_password(student_data['password'])
                        if not student_created:
                            django_user.first_name = student_data['full_name']
                        django_user.save()

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
                            contract.course_level = student_data['course_level']
                            contract.contract_amount = student_data['contract_amount']
                            contract.paid_amount = student_data['paid_amount']
                            contract.is_grant = student_data['contract_amount'] == 0
                            contract.save(update_fields=['course_level', 'contract_amount', 'paid_amount', 'is_grant'])
                            TutorPaymentConfirmation.objects.filter(
                                contract=contract, is_active=True
                            ).update(is_active=False)

                        if student_created:
                            created_count += 1
                        else:
                            updated_count += 1

                except Exception as e:
                    row_errors.append(f"ID {student_data.get('student_id', '?')}: {e}")

            # Har guruh import qilinganda snapshot olish
            try:
                _take_snapshot(group, academic_year)
            except Exception:
                pass

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
        agg = StudentContract.objects.filter(academic_year=current_year).aggregate(
            total_contract=Sum('contract_amount'),
            total_paid=Sum('paid_amount'),
        )
        total_contract = agg['total_contract'] or 0
        total_paid = agg['total_paid'] or 0
        total_debt = total_contract - total_paid

        # To'lov snapshot tarixi (oxirgi 10 ta)
        snapshot_rows = (
            PaymentSnapshot.objects
            .filter(academic_year=current_year)
            .values('snapshot_date')
            .annotate(
                t25=Sum('tier_25'), t50=Sum('tier_50'),
                t75=Sum('tier_75'), t100=Sum('tier_100'),
            )
            .order_by('-snapshot_date')[:10]
        )

        # Joriy holat: tier counts
        current_tier_counts = _current_tier_counts(all_groups, current_year)

        context = {
            'groups_data': groups_data,
            'current_year': current_year,
            'total_students': total_students,
            'total_contract': total_contract,
            'total_paid': total_paid,
            'total_debt': total_debt,
            'groups_count': all_groups.count(),
            'snapshot_rows': snapshot_rows,
            'tier_counts': current_tier_counts,
        }
        return render(request, 'dashboard/admin_overview.html', context)


def _current_tier_counts(groups, academic_year):
    """Joriy o'quv yilida har tierdagi talabalar sonini hisoblaydi."""
    t = {0: 0, 25: 0, 50: 0, 75: 0, 100: 0}
    for student in Student.objects.filter(group__in=groups):
        contract = student.contracts.filter(academic_year=academic_year).first()
        tier = _calc_tier(_calc_pct(contract))
        t[tier] = t.get(tier, 0) + 1
    return t


# ---------------------------------------------------------------------------
# To'lov statistikasi (katta jadval)
# ---------------------------------------------------------------------------

@method_decorator(login_required(login_url='/dashboard/login/'), name='dispatch')
class PaymentStatsView(View):
    def get(self, request):
        current_year = current_academic_year()
        all_groups = get_accessible_groups(request.user)

        # Filters
        group_filter  = request.GET.get('group', '').strip()
        display_mode  = request.GET.get('mode', 'count')    # count | pct
        view_mode     = request.GET.get('view', 'simple')   # simple | detail
        do_export     = request.GET.get('export', '')

        # Detail view filters
        tier_filter   = request.GET.get('tier', '').strip()
        search        = request.GET.get('q', '').strip()
        sort_by       = request.GET.get('sort', 'pct')
        sort_dir      = request.GET.get('dir', 'desc')

        groups_qs = all_groups
        if group_filter:
            groups_qs = groups_qs.filter(pk=group_filter)

        # ─── Joriy holat (live) ─── always calculated, used in simple view
        current_tier_counts = _current_tier_counts(groups_qs, current_year)

        # ─── Snapshot history (for simple view) ───
        snap_qs = PaymentSnapshot.objects.filter(
            academic_year=current_year, group__in=groups_qs
        )
        snapshot_rows = list(
            snap_qs
            .values('snapshot_date')
            .annotate(
                t25=Sum('tier_25'), t50=Sum('tier_50'),
                t75=Sum('tier_75'), t100=Sum('tier_100'),
            )
            .order_by('-snapshot_date')[:20]
        )

        # ─── Detail view (only built if needed) ───
        page_obj = None
        total_rows = 0
        rows = []

        if view_mode == 'detail' or do_export:
            students_qs = (
                Student.objects
                .filter(group__in=groups_qs)
                .select_related('group')
                .prefetch_related('contracts')
            )
            if search:
                students_qs = students_qs.filter(
                    Q(full_name__icontains=search) | Q(student_id__icontains=search)
                )

            for student in students_qs:
                contract = student.contracts.filter(academic_year=current_year).first()
                pct  = _calc_pct(contract)
                tier = _calc_tier(pct)
                paid  = float(contract.paid_amount)     if contract else 0
                total = float(contract.contract_amount) if contract else 0
                debt  = float(contract.debt_amount)     if contract else 0
                rows.append({
                    'student': student, 'contract': contract,
                    'pct': round(min(pct, 100), 1),
                    'tier': tier, 'paid': paid, 'total': total, 'debt': debt,
                })

            if tier_filter != '':
                try:
                    tf = int(tier_filter)
                    rows = [r for r in rows if r['tier'] == tf]
                except ValueError:
                    pass

            reverse = (sort_dir == 'desc')
            if sort_by == 'name':
                rows.sort(key=lambda r: r['student'].full_name, reverse=reverse)
            elif sort_by in ('pct', 'paid', 'debt'):
                rows.sort(key=lambda r: r.get(sort_by, 0), reverse=reverse)

            total_rows = len(rows)

            if do_export == 'xlsx':
                return self._export_excel(rows, snapshot_rows, current_tier_counts, current_year)

            paginator = Paginator(rows, 100)
            page_obj  = paginator.get_page(request.GET.get('page', 1))

        next_dir = 'asc' if sort_dir == 'desc' else 'desc'
        context = {
            'all_groups': all_groups,
            'group_filter': group_filter,
            'display_mode': display_mode,
            'view_mode': view_mode,
            'current_tier_counts': current_tier_counts,
            'snapshot_rows': snapshot_rows,
            'page_obj': page_obj,
            'total_rows': total_rows,
            'search': search,
            'tier_filter': tier_filter,
            'sort_by': sort_by,
            'sort_dir': sort_dir,
            'next_dir': next_dir,
            'current_year': current_year,
        }
        return render(request, 'dashboard/payment_stats.html', context)

    # ---- Excel export (2 sheet: snapshot + students) ----
    def _export_excel(self, rows, snapshot_rows, current_tier_counts, academic_year):
        wb = openpyxl.Workbook()
        hdr_fill = PatternFill("solid", fgColor="1E293B")
        hdr_font = Font(bold=True, color="FFFFFF")
        center   = Alignment(horizontal='center')

        # ───── Sheet 1: Snapshot tarixi ─────
        ws1 = wb.active
        ws1.title = "To'lov dinamikasi"
        snap_headers = ['Sana', "25% to'lov", "50% to'lov", "75% to'lov", "100% to'lov", "Jami"]
        for col, h in enumerate(snap_headers, 1):
            cell = ws1.cell(row=1, column=col, value=h)
            cell.fill, cell.font, cell.alignment = hdr_fill, hdr_font, center

        # Joriy holat birinchi qator
        t = current_tier_counts
        ws1.append(['Joriy holat', t.get(25,0), t.get(50,0), t.get(75,0), t.get(100,0),
                    t.get(0,0)+t.get(25,0)+t.get(50,0)+t.get(75,0)+t.get(100,0)])

        for row in snapshot_rows:
            total = row['t25'] + row['t50'] + row['t75'] + row['t100']
            ws1.append([
                row['snapshot_date'].strftime('%d.%m.%Y'),
                row['t25'], row['t50'], row['t75'], row['t100'], total,
            ])

        for col_idx, width in enumerate([16, 14, 14, 14, 14, 10], 1):
            ws1.column_dimensions[get_column_letter(col_idx)].width = width

        # ───── Sheet 2: Talabalar ro'yxati ─────
        ws2 = wb.create_sheet("Talabalar")
        headers = ['#', 'F.I.O', 'ID', 'Guruh', 'Kurs',
                   "Kontrakt (so'm)", "To'langan (so'm)", "Qarz (so'm)", "Foiz (%)", "Tier"]
        for col, h in enumerate(headers, 1):
            cell = ws2.cell(row=1, column=col, value=h)
            cell.fill, cell.font, cell.alignment = hdr_fill, hdr_font, center

        tier_labels = {0: 'Toʻlamagan (<25%)', 25: '25% tier', 50: '50% tier',
                       75: '75% tier', 100: '100% tier'}
        for i, r in enumerate(rows, 1):
            s, c = r['student'], r['contract']
            ws2.append([
                i, s.full_name, s.student_id,
                s.group.name if s.group else '',
                c.course_level if c else '',
                r['total'], r['paid'], r['debt'], r['pct'],
                tier_labels.get(r['tier'], ''),
            ])
        for col_idx, width in enumerate([5, 30, 15, 12, 7, 18, 18, 18, 10, 18], 1):
            ws2.column_dimensions[get_column_letter(col_idx)].width = width

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="payment_stats_{academic_year}.xlsx"'
        return response


# ---------------------------------------------------------------------------
# Xabarnoma yuborish (bulk campaign)
# ---------------------------------------------------------------------------

@method_decorator(login_required(login_url='/dashboard/login/'), name='dispatch')
class CampaignSendView(View):
    def get(self, request):
        all_groups = get_accessible_groups(request.user)
        failures_count = NotificationFailure.objects.count()
        context = {
            'all_groups': all_groups,
            'failures_count': failures_count,
        }
        return render(request, 'dashboard/campaign_send.html', context)

    def post(self, request):
        from users.tasks import send_telegram_message as _send_msg

        group_ids      = request.POST.getlist('groups')
        recipient_type = request.POST.get('recipient_type', 'student_only')
        tier_filter    = int(request.POST.get('tier_filter', 0))
        student_type   = request.POST.get('student_type', 'all')
        message_text   = request.POST.get('message_text', '').strip()

        if not group_ids or not message_text:
            messages.error(request, "Kamida bitta guruh tanlang va xabar kiriting.")
            return redirect('dashboard:campaign_send')

        # Faqat ruxsat berilgan guruhlarga cheklash
        accessible_ids = list(
            get_accessible_groups(request.user).values_list('pk', flat=True)
        )
        group_ids = [gid for gid in group_ids if int(gid) in accessible_ids]

        students = (
            Student.objects
            .filter(group__in=group_ids)
            .select_related('group')
            .prefetch_related('contracts', 'parents__parent')
        )
        if student_type == 'contract_only':
            students = students.filter(contracts__is_grant=False).distinct()
        elif student_type == 'grant_only':
            students = students.filter(contracts__is_grant=True).distinct()

        current_year = current_academic_year()
        sent = failed = skipped = 0

        for student in students:
            # Tier filter: faqat shuncha % kam to'laganlar
            if tier_filter > 0:
                contract = student.contracts.filter(academic_year=current_year).first()
                if contract and contract.contract_amount > 0:
                    pct = float(contract.paid_amount) / float(contract.contract_amount) * 100
                    if pct >= tier_filter:
                        skipped += 1
                        continue

            # Tutor tasdiqlagan bo'lsa o'tkazib yuboramiz
            if TutorPaymentConfirmation.objects.filter(
                contract__student=student, is_active=True
            ).exists():
                skipped += 1
                continue

            student_text = (
                f"📢 <b>Xabarnoma</b>\n\n"
                f"Hurmatli <b>{student.full_name}</b>,\n\n"
                f"{message_text}"
            )

            # Talabaning o'ziga
            if recipient_type in ('student_only', 'student_and_parent'):
                if student.telegram_id:
                    ok = _send_msg(student.telegram_id, student_text, student=student)
                    sent += 1 if ok else 0
                    failed += 0 if ok else 1
                else:
                    skipped += 1

            # Ota-onaga
            if recipient_type in ('parent_only', 'student_and_parent'):
                for rel in student.parents.filter(status='verified').select_related('parent'):
                    if rel.parent.telegram_id:
                        parent_text = (
                            f"📢 <b>Xabarnoma</b>\n\n"
                            f"Hurmatli ota-ona, farzandingiz "
                            f"<b>{student.full_name}</b> haqida:\n\n"
                            f"{message_text}"
                        )
                        ok = _send_msg(rel.parent.telegram_id, parent_text, parent=rel.parent)
                        sent += 1 if ok else 0
                        failed += 0 if ok else 1
                    else:
                        skipped += 1

        if failed:
            messages.warning(
                request,
                f"Yuborildi: {sent} ta ✅  |  Xato: {failed} ta ❌  |  O'tkazib: {skipped} ta"
            )
        else:
            messages.success(
                request,
                f"Muvaffaqiyatli yuborildi: {sent} ta ✅  |  O'tkazib: {skipped} ta"
            )
        return redirect('dashboard:campaign_send')


# ---------------------------------------------------------------------------
# Ota-onalar sahifasi
# ---------------------------------------------------------------------------

@method_decorator(login_required(login_url='/dashboard/login/'), name='dispatch')
class ParentsView(View):
    def get(self, request):
        groups = get_accessible_groups(request.user)

        search        = request.GET.get('q', '').strip()
        group_filter  = request.GET.get('group', '')
        status_filter = request.GET.get('status', '')

        if group_filter:
            groups = groups.filter(pk=group_filter)

        students_qs = Student.objects.filter(
            group__in=groups
        ).select_related('group').prefetch_related(
            'parents__parent', 'parents__tutor_verification',
        )

        if search:
            students_qs = students_qs.filter(
                Q(full_name__icontains=search) |
                Q(student_id__icontains=search) |
                Q(parents__parent__phone_number__icontains=search) |
                Q(parents__parent__full_name__icontains=search)
            ).distinct()

        rows = []
        for student in students_qs:
            relations = list(student.parents.all())

            if status_filter == 'no_parent' and relations:
                continue
            if status_filter == 'no_parent' and not relations:
                rows.append({'student': student, 'relations': [], 'no_parent': True})
                continue

            filtered_rels = []
            for rel in relations:
                tutor_ver = getattr(rel, 'tutor_verification', None)
                rel_data = {
                    'rel': rel,
                    'tutor_verified': tutor_ver is not None,
                    'tutor_ver': tutor_ver,
                }
                if status_filter == 'tutor_verified' and not rel_data['tutor_verified']:
                    continue
                if status_filter == 'verified' and rel.status != 'verified':
                    continue
                if status_filter == 'pending_otp' and rel.status != 'pending_otp':
                    continue
                filtered_rels.append(rel_data)

            if status_filter in ('verified', 'pending_otp', 'tutor_verified') and not filtered_rels:
                continue

            rows.append({
                'student': student,
                'relations': filtered_rels,
                'no_parent': len(relations) == 0,
            })

        all_groups = get_accessible_groups(request.user)
        context = {
            'rows': rows,
            'search': search,
            'group_filter': group_filter,
            'status_filter': status_filter,
            'all_groups': all_groups,
        }
        return render(request, 'dashboard/parents.html', context)


@method_decorator(login_required(login_url='/dashboard/login/'), name='dispatch')
class VerifyParentView(View):
    def post(self, request, sp_id):
        sp = get_object_or_404(StudentParent, pk=sp_id)
        if not can_access_student(request.user, sp.student):
            messages.error(request, "Sizda bu talabaga kirish huquqi yo'q.")
            return redirect('dashboard:parents')

        note = request.POST.get('note', '').strip()
        ParentTutorVerification.objects.update_or_create(
            student_parent=sp,
            defaults={'verified_by': request.user, 'note': note}
        )
        messages.success(
            request,
            f"{sp.parent.full_name or sp.parent.phone_number} — maksimal darajada tasdiqlandi."
        )
        return redirect(request.POST.get('next', 'dashboard:parents'))


@method_decorator(login_required(login_url='/dashboard/login/'), name='dispatch')
class UnverifyParentView(View):
    def post(self, request, sp_id):
        sp = get_object_or_404(StudentParent, pk=sp_id)
        if not can_access_student(request.user, sp.student):
            messages.error(request, "Sizda bu talabaga kirish huquqi yo'q.")
            return redirect('dashboard:parents')

        ParentTutorVerification.objects.filter(student_parent=sp).delete()
        messages.info(request, "Tutor tasdiqlashi bekor qilindi.")
        return redirect(request.POST.get('next', 'dashboard:parents'))


# ---------------------------------------------------------------------------
# Xabarnoma xatolari
# ---------------------------------------------------------------------------

@method_decorator(login_required(login_url='/dashboard/login/'), name='dispatch')
class NotificationFailuresView(View):
    def get(self, request):
        type_filter = request.GET.get('type', '')
        search      = request.GET.get('q', '').strip()

        failures_qs = NotificationFailure.objects.select_related('student__group', 'parent', 'campaign')

        if not request.user.is_staff:
            accessible_groups = get_accessible_groups(request.user)
            failures_qs = failures_qs.filter(
                Q(student__group__in=accessible_groups) |
                Q(parent__students__student__group__in=accessible_groups)
            ).distinct()

        if type_filter == 'student':
            failures_qs = failures_qs.filter(recipient_type='student')
        elif type_filter == 'parent':
            failures_qs = failures_qs.filter(recipient_type='parent')

        if search:
            failures_qs = failures_qs.filter(
                Q(student__full_name__icontains=search) |
                Q(student__student_id__icontains=search) |
                Q(parent__full_name__icontains=search) |
                Q(parent__phone_number__icontains=search)
            )

        context = {
            'failures': failures_qs,
            'type_filter': type_filter,
            'search': search,
            'student_count': NotificationFailure.objects.filter(recipient_type='student').count(),
            'parent_count': NotificationFailure.objects.filter(recipient_type='parent').count(),
        }
        return render(request, 'dashboard/notification_failures.html', context)

    def post(self, request):
        failure_id = request.POST.get('failure_id')
        if failure_id:
            NotificationFailure.objects.filter(pk=failure_id).delete()
            messages.success(request, "Yozuv o'chirildi.")
        return redirect('dashboard:notification_failures')
