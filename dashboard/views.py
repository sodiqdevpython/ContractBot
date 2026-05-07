import io
import json
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
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

from users.models import Group, Student, StudentContract, Payment, StudentParent, Parent, current_academic_year, NotificationCampaign
from .models import TutorPaymentConfirmation, ParentTutorVerification, NotificationFailure, PaymentSnapshot
from .excel_parser import parse_multi_group_excel
from .forms import LoginForm, ExcelImportForm, ConfirmPaymentForm, NotificationCampaignForm


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
        confirmed_amount_raw = request.POST.get('confirmed_amount', '').strip()
        confirmed_amount = None
        if confirmed_amount_raw:
            try:
                from decimal import Decimal
                confirmed_amount = Decimal(confirmed_amount_raw.replace(' ', '').replace(',', '.'))
            except Exception:
                pass
        TutorPaymentConfirmation.objects.create(
            contract=contract,
            confirmed_by=request.user,
            is_active=True,
            note=note,
            confirmed_amount=confirmed_amount,
        )
        amount_str = f" ({confirmed_amount:,.0f} so'm)" if confirmed_amount else ""
        messages.success(request, f"{student.full_name} uchun to'lov{amount_str} tasdiqlandi. Xabarnomalar to'xtatildi.")
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

                        from decimal import Decimal as _D
                        from django.utils import timezone as _tz

                        # Yangi to'lov miqdorini oldindan saqlab qo'yamiz
                        new_paid = _D(str(student_data['paid_amount']))

                        contract, contract_created = StudentContract.objects.get_or_create(
                            student=student,
                            academic_year=academic_year,
                            defaults={
                                'course_level': student_data['course_level'],
                                'contract_amount': student_data['contract_amount'],
                                'paid_amount': new_paid,
                                'is_grant': student_data['contract_amount'] == 0,
                            }
                        )

                        if not contract_created:
                            old_paid = _D(str(contract.paid_amount))
                            contract.course_level = student_data['course_level']
                            contract.contract_amount = student_data['contract_amount']
                            contract.paid_amount = new_paid
                            contract.is_grant = student_data['contract_amount'] == 0
                            contract.save(update_fields=['course_level', 'contract_amount', 'paid_amount', 'is_grant'])
                            TutorPaymentConfirmation.objects.filter(
                                contract=contract, is_active=True
                            ).update(is_active=False)

                            # To'lov miqdori oshgan bo'lsa — tarix yozuvi (bulk_create: save() ni chaqirmaydi)
                            delta = new_paid - old_paid
                            if delta > 0:
                                Payment.objects.bulk_create([Payment(
                                    contract=contract,
                                    amount=delta,
                                    payment_date=_tz.localdate(),
                                )])
                        else:
                            # Yangi kontrakt — agar to'lov bo'lsa, dastlabki yozuv
                            if new_paid > 0:
                                Payment.objects.bulk_create([Payment(
                                    contract=contract,
                                    amount=new_paid,
                                    payment_date=_tz.localdate(),
                                )])

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

        # ─── Delta (o'sish hisoblash) ───
        for i, row in enumerate(snapshot_rows):
            if i + 1 < len(snapshot_rows):
                prev = snapshot_rows[i + 1]
                row['d25']  = row['t25']  - prev['t25']
                row['d50']  = row['t50']  - prev['t50']
                row['d75']  = row['t75']  - prev['t75']
                row['d100'] = row['t100'] - prev['t100']
            else:
                row['d25'] = row['d50'] = row['d75'] = row['d100'] = None

        # ─── Chart data (oldest → newest) ───
        chart_list = list(reversed(snapshot_rows))
        t = current_tier_counts
        chart_labels = [r['snapshot_date'].strftime('%d.%m') for r in chart_list] + ['Hozir']
        chart_t25  = [r['t25']  for r in chart_list] + [t.get(25,  0)]
        chart_t50  = [r['t50']  for r in chart_list] + [t.get(50,  0)]
        chart_t75  = [r['t75']  for r in chart_list] + [t.get(75,  0)]
        chart_t100 = [r['t100'] for r in chart_list] + [t.get(100, 0)]

        # ─── Detail view (only built if needed) ───
        page_obj = None
        total_rows = 0
        rows = []

        if view_mode == 'detail' or do_export:
            students_qs = (
                Student.objects
                .filter(group__in=groups_qs)
                .select_related('group')
                .prefetch_related('contracts__tutor_confirmations', 'parents')
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
                has_confirmation = (
                    any(tc.is_active for tc in contract.tutor_confirmations.all())
                    if contract else False
                )
                has_parent = any(rel.status == 'verified' for rel in student.parents.all())
                rows.append({
                    'student': student, 'contract': contract,
                    'pct': round(min(pct, 100), 1),
                    'tier': tier, 'paid': paid, 'total': total, 'debt': debt,
                    'has_telegram':     bool(student.telegram_id),
                    'has_confirmation': has_confirmation,
                    'has_parent':       has_parent,
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
            # Chart.js uchun JSON
            'chart_labels_json': json.dumps(chart_labels),
            'chart_t25_json':    json.dumps(chart_t25),
            'chart_t50_json':    json.dumps(chart_t50),
            'chart_t75_json':    json.dumps(chart_t75),
            'chart_t100_json':   json.dumps(chart_t100),
        }
        return render(request, 'dashboard/payment_stats.html', context)

    # ---- Excel export — minimalistik, ko'proq ma'lumot ----
    def _export_excel(self, rows, snapshot_rows, current_tier_counts, academic_year):
        wb = openpyxl.Workbook()

        thin   = Side(border_style='thin', color='CBD5E1')
        brd    = Border(left=thin, right=thin, top=thin, bottom=thin)
        hdr_f  = Font(bold=True, name='Calibri', size=10, color='1E293B')
        hdr_bg = PatternFill('solid', fgColor='F1F5F9')
        c_aln  = Alignment(horizontal='center', vertical='center', wrap_text=False)
        l_aln  = Alignment(horizontal='left',   vertical='center')

        def _cell(ws, row, col, val, font=None, fill=None, aln=None):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = brd
            if font: cell.font = font
            if fill: cell.fill = fill
            if aln:  cell.alignment = aln
            return cell

        # ─── Sheet 1: Snapshot tarixi + delta ───
        ws1 = wb.active
        ws1.title = "To'lov dinamikasi"
        ws1.freeze_panes = 'A2'
        ws1.row_dimensions[1].height = 22

        s1_hdrs = [
            'Sana',
            "25% bosqich", "50% bosqich",
            "75% bosqich", "100% to'lagan",
            'Jami',
        ]
        for c, h in enumerate(s1_hdrs, 1):
            _cell(ws1, 1, c, h, font=hdr_f, fill=hdr_bg, aln=c_aln)

        def _fmt_delta(d):
            if d is None: return '—'
            return f'+{d}' if d > 0 else (str(d) if d != 0 else '0')

        # Joriy holat
        t = current_tier_counts
        total0 = t.get(0,0)+t.get(25,0)+t.get(50,0)+t.get(75,0)+t.get(100,0)
        row0 = ['Joriy holat', t.get(25,0), t.get(50,0), t.get(75,0), t.get(100,0), total0]
        bold10 = Font(bold=True, name='Calibri', size=10)
        for c, v in enumerate(row0, 1):
            _cell(ws1, 2, c, v, font=bold10, aln=c_aln if c > 1 else l_aln)

        for i, row in enumerate(snapshot_rows, 3):
            sd = row['snapshot_date']
            sdt = sd.strftime('%d.%m.%Y') if hasattr(sd, 'strftime') else str(sd)
            total = row['t25'] + row['t50'] + row['t75'] + row['t100']
            rd = [sdt, row['t25'], row['t50'], row['t75'], row['t100'], total]
            for c, v in enumerate(rd, 1):
                _cell(ws1, i, c, v, aln=c_aln if c > 1 else l_aln)

        for ci, w in enumerate([16, 14, 14, 14, 16, 10], 1):
            ws1.column_dimensions[get_column_letter(ci)].width = w

        # ─── Sheet 2: Talabalar ro'yxati ───
        ws2 = wb.create_sheet("Talabalar ro'yxati")
        ws2.freeze_panes = 'A2'
        ws2.row_dimensions[1].height = 22

        s2_hdrs = [
            '#', 'F.I.O', 'Talaba ID', 'Guruh', 'Kurs',
            "Kontrakt (so'm)", "To'langan (so'm)", "Qarz (so'm)",
            'Foiz (%)', 'Tier',
            'Telegram', 'Tutor tasdiq', 'Ota-ona',
        ]
        for c, h in enumerate(s2_hdrs, 1):
            _cell(ws2, 1, c, h, font=hdr_f, fill=hdr_bg, aln=c_aln)

        tier_lbl = {0:"To'lamagan (<25%)", 25:"25% bosqich", 50:"50% bosqich", 75:"75% bosqich", 100:"To'liq to'lagan"}
        for i, r in enumerate(rows, 1):
            s, c = r['student'], r['contract']
            rd = [
                i, s.full_name, s.student_id,
                s.group.name if s.group else '',
                c.course_level if c else '',
                float(r['total']), float(r['paid']), float(r['debt']),
                r['pct'], tier_lbl.get(r['tier'], ''),
                'Ha' if r.get('has_telegram')     else "Yo'q",
                'Ha' if r.get('has_confirmation') else "Yo'q",
                'Ha' if r.get('has_parent')       else "Yo'q",
            ]
            for ci, v in enumerate(rd, 1):
                _cell(ws2, i+1, ci, v, aln=l_aln if ci == 2 else c_aln)

        for ci, w in enumerate([5,32,14,12,7,18,18,18,10,12,10,12,10], 1):
            ws2.column_dimensions[get_column_letter(ci)].width = w

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
    def _get_accessible_scheduled(self, user):
        """Foydalanuvchi ruxsatiga ko'ra rejalashtirilgan kampaniyalar."""
        all_groups = get_accessible_groups(user)
        return (
            NotificationCampaign.objects
            .filter(groups__in=all_groups)
            .distinct()
            .prefetch_related('groups')
            .order_by('start_date', 'send_time')
        )

    def get(self, request):
        from django.utils import timezone as _tz
        all_groups = get_accessible_groups(request.user)
        failures_count = NotificationFailure.objects.count()
        scheduled_campaigns = self._get_accessible_scheduled(request.user)
        context = {
            'all_groups': all_groups,
            'failures_count': failures_count,
            'scheduled_campaigns': scheduled_campaigns,
            'today_str': _tz.localdate().isoformat(),
        }
        return render(request, 'dashboard/campaign_send.html', context)

    def post(self, request):
        action    = request.POST.get('action', '')
        send_mode = request.POST.get('send_mode', 'now')

        # ── 1. Rejalashtirilgan kampaniyani o'chirish ──────────────────────
        if action == 'delete_schedule':
            camp_id = request.POST.get('campaign_id')
            if camp_id:
                accessible_ids = list(
                    get_accessible_groups(request.user).values_list('pk', flat=True)
                )
                camp = NotificationCampaign.objects.filter(pk=camp_id).first()
                if camp and camp.groups.filter(pk__in=accessible_ids).exists():
                    camp.delete()
                    messages.success(request, "Rejalashtirilgan xabarnoma o'chirildi.")
                else:
                    messages.error(request, "Kampaniya topilmadi yoki ruxsat yo'q.")
            return redirect('dashboard:campaign_send')

        # ── Umumiy maydonlar ───────────────────────────────────────────────
        group_ids      = request.POST.getlist('groups')
        recipient_type = request.POST.get('recipient_type', 'student_only')
        tier_filter    = int(request.POST.get('tier_filter', 0) or 0)
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
        if not group_ids:
            messages.error(request, "Tanlangan guruhlar uchun ruxsat yo'q.")
            return redirect('dashboard:campaign_send')

        # ── 2. Rejalashtirilgan yuborish — kampaniya yaratish ──────────────
        if send_mode == 'scheduled':
            from datetime import date as _date, time as _time
            start_date_str = request.POST.get('scheduled_start_date', '').strip()
            end_date_str   = request.POST.get('scheduled_end_date', '').strip()
            time_str       = request.POST.get('scheduled_time', '09:00').strip()

            if not start_date_str or not end_date_str:
                messages.error(request, "Boshlanish va tugash sanalarini kiriting.")
                return redirect('dashboard:campaign_send')

            try:
                sched_start = _date.fromisoformat(start_date_str)
                sched_end   = _date.fromisoformat(end_date_str)
            except ValueError:
                messages.error(request, "Noto'g'ri sana formati.")
                return redirect('dashboard:campaign_send')

            if sched_end < sched_start:
                messages.error(request, "Tugash sanasi boshlanish sanasidan kichik bo'lmasligi kerak.")
                return redirect('dashboard:campaign_send')

            try:
                parts = time_str.split(':')
                sched_time = _time(int(parts[0]), int(parts[1]))
            except Exception:
                sched_time = _time(9, 0)

            camp = NotificationCampaign.objects.create(
                start_date=sched_start,
                end_date=sched_end,
                send_time=sched_time,
                message_text=message_text,
                recipients=recipient_type,
                target_debt_tier=tier_filter,
                student_type_filter=student_type,
            )
            camp.groups.set(group_ids)

            if sched_start == sched_end:
                date_info = f"{sched_start.strftime('%d.%m.%Y')} kuni"
            else:
                date_info = f"{sched_start.strftime('%d.%m.%Y')} — {sched_end.strftime('%d.%m.%Y')} kunlari har kuni"

            messages.success(
                request,
                f"Xabarnoma {date_info} soat {sched_time.strftime('%H:%M')} da "
                f"yuborilish uchun rejalashtirildi ✅"
            )
            return redirect('dashboard:campaign_send')

        # ── 3. Hozir yuborish ──────────────────────────────────────────────
        from users.tasks import send_telegram_message as _send_msg

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
            # bosqich filtri: faqat shuncha % kam to'laganlar
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
            f"{sp.parent.full_name or sp.parent.phone_number} — maksimal tierda tasdiqlandi."
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


# ---------------------------------------------------------------------------
# Rejalashtirilgan xabarnomalar (NotificationCampaign)
# ---------------------------------------------------------------------------

@method_decorator(login_required(login_url='/dashboard/login/'), name='dispatch')
class CampaignScheduleView(View):
    def get(self, request):
        all_groups = get_accessible_groups(request.user)
        form = NotificationCampaignForm(accessible_groups=all_groups)

        # Faqat shu foydalanuvchi ko'ra oladigan kampaniyalar
        campaigns = (
            NotificationCampaign.objects
            .filter(groups__in=all_groups)
            .distinct()
            .prefetch_related('groups')
            .order_by('-start_date')
        )

        context = {
            'form': form,
            'campaigns': campaigns,
            'all_groups': all_groups,
        }
        return render(request, 'dashboard/campaign_schedule.html', context)

    def post(self, request):
        all_groups = get_accessible_groups(request.user)
        action = request.POST.get('action', 'create')

        if action == 'delete':
            camp_id = request.POST.get('campaign_id')
            if camp_id:
                camp = NotificationCampaign.objects.filter(pk=camp_id).first()
                if camp and camp.groups.filter(pk__in=all_groups).exists():
                    camp.delete()
                    messages.success(request, "Kampaniya o'chirildi.")
                else:
                    messages.error(request, "Kampaniya topilmadi yoki ruxsatsiz.")
            return redirect('dashboard:campaign_schedule')

        form = NotificationCampaignForm(request.POST, accessible_groups=all_groups)
        if form.is_valid():
            # Faqat ruxsat berilgan guruhlar tanlanishi mumkin
            camp = form.save(commit=False)
            camp.save()
            selected_groups = form.cleaned_data['groups'].filter(pk__in=all_groups)
            camp.groups.set(selected_groups)
            messages.success(
                request,
                f"Kampaniya {camp.start_date} — {camp.end_date} davri uchun yaratildi."
            )
            return redirect('dashboard:campaign_schedule')
        else:
            campaigns = (
                NotificationCampaign.objects
                .filter(groups__in=all_groups)
                .distinct()
                .prefetch_related('groups')
                .order_by('-start_date')
            )
            return render(request, 'dashboard/campaign_schedule.html', {
                'form': form, 'campaigns': campaigns, 'all_groups': all_groups,
            })


# ---------------------------------------------------------------------------
# Excel yuklash shablonini yuklab olish
# ---------------------------------------------------------------------------

@method_decorator(login_required(login_url='/dashboard/login/'), name='dispatch')
class ExcelTemplateView(View):
    def get(self, request):
        wb = openpyxl.Workbook()

        thin   = Side(border_style='thin', color='CBD5E1')
        brd    = Border(left=thin, right=thin, top=thin, bottom=thin)
        c_aln  = Alignment(horizontal='center', vertical='center')
        l_aln  = Alignment(horizontal='left',   vertical='center')

        ws = wb.active
        ws.title = "Shablon"

        col_widths = {'A': 14, 'B': 14, 'C': 30, 'D': 8, 'E': 18, 'F': 18}
        for col, w in col_widths.items():
            ws.column_dimensions[col].width = w

        col_headers = ['login', 'parol', 'F.I.O', 'kurs', "kontrakt (so'm)", "to'langan (so'm)"]

        def write_group(start_row, group_name, students):
            # Guruh nomi
            cell = ws.cell(row=start_row, column=1, value=group_name)
            cell.font  = Font(bold=True, size=11, color='4338CA')
            cell.fill  = PatternFill('solid', fgColor='EDE9FE')
            cell.alignment = l_aln
            ws.merge_cells(f'A{start_row}:F{start_row}')
            ws.row_dimensions[start_row].height = 20

            # Ustun sarlavhalari (parser o'tkazib yuboradi)
            for ci, h in enumerate(col_headers, 1):
                c = ws.cell(row=start_row + 1, column=ci, value=h)
                c.font      = Font(bold=True, size=9, color='64748B', italic=True)
                c.fill      = PatternFill('solid', fgColor='F8FAFC')
                c.border    = brd
                c.alignment = c_aln

            # Ma'lumot qatorlari
            for ri, row_data in enumerate(students):
                rn = start_row + 2 + ri
                for ci, val in enumerate(row_data, 1):
                    c = ws.cell(row=rn, column=ci, value=val)
                    c.border    = brd
                    c.alignment = l_aln if ci == 3 else c_aln
                ws.row_dimensions[rn].height = 16

            return start_row + 2 + len(students) + 1  # keyingi guruh boshlanishi

        nxt = write_group(1, 'ki-23-1', [
            ('s001', 'pass001', 'Aliyev Ali Vali',      1, 5_000_000, 2_500_000),
            ('s002', 'pass002', 'Karimova Zulfiya',     1, 5_000_000, 5_000_000),
            ('s003', 'pass003', 'Nazarov Bobur Salim',  1, 5_000_000, 0),
        ])
        write_group(nxt, 'ki-23-2', [
            ('s101', 'pass101', 'Rahimov Sherzod',      2, 6_000_000, 3_000_000),
            ('s102', 'pass102', "Toshmatova Nodira",    2, 6_000_000, 6_000_000),
            ('s103', 'pass103', 'Usmonov Jasur',        2, 0,         0),  # grant
        ])

        # Ko'rsatmalar varag'i
        ws2 = wb.create_sheet("Ko'rsatmalar")
        ws2.column_dimensions['A'].width = 65
        lines = [
            "EXCEL YUKLASH — KO'RSATMALAR",
            "",
            "Har bir guruh quyidagi tartibda yoziladi:",
            "  1. A ustuniga guruh nomini yozing  (masalan: ki-23-1, mt-22-3)",
            "  2. Keyin sarlavha qatori (parser o'tkazib yuboradi — siz ko'rish uchun foydali)",
            "  3. Keyin talabalar ma'lumotlari:",
            "",
            "     A — login (talaba ID, unikal)",
            "     B — parol",
            "     C — F.I.O (to'liq ism)",
            "     D — kurs (1, 2, 3 yoki 4)",
            "     E — kontrakt summasi so'mda  (0 = grant talaba)",
            "     F — to'langan summa so'mda",
            "",
            "Guruhlar orasida bo'sh qator qoldirishingiz mumkin.",
            "Bir faylga bir nechta guruh sig'adi.",
            "",
            "MUHIM:",
            "  - Guruh nomi tizimda mavjud bo'lishi shart",
            "  - Mavjud talabalar yangilanadi, tutor tasdiqlari bekor qilinadi",
            "  - Grant talabalar uchun kontrakt = 0 deb yozing",
        ]
        for i, line in enumerate(lines, 1):
            cell = ws2.cell(row=i, column=1, value=line)
            if i == 1:
                cell.font = Font(bold=True, size=12)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="excel_yuklash_shablon.xlsx"'
        return response
