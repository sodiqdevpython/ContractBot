import re
from decimal import Decimal, InvalidOperation
import openpyxl

# Format: xx-xx-x yoki xx-xx-xx (2 harf, 2 raqam, 1-2 raqam)
GROUP_PATTERN = re.compile(r'^[a-z]{2}-\d{2}-\d{1,2}$')


def parse_multi_group_excel(file):
    """
    Bir yoki bir nechta guruhlarni o'z ichiga olgan Excel faylini tahlil qiladi.

    Fayl formati:
        [bo'sh qator - ixtiyoriy]
        ki-23-1        <- guruh nomi (column A, kichik harf)
        1  2  3  4  5  6   <- sarlavha qatori (o'tkazib yuboriladi)
        s001 pass Ali 1 5000000 0  <- ma'lumot qatori
        ...
        ki-23-2        <- keyingi guruh
        ...

    Qaytaradi: {group_name: [{'student_id': ..., 'password': ..., ...}, ...]}
    """
    wb = openpyxl.load_workbook(file, data_only=True)
    ws = wb.active

    result = {}
    current_group = None
    skip_next_as_header = False

    for row in ws.iter_rows(values_only=True):
        # Bo'sh qatorlarni o'tkazib yuboramiz
        if all(cell is None or str(cell).strip() == '' for cell in row):
            continue

        first_cell = str(row[0]).strip().lower() if row[0] is not None else ''

        if GROUP_PATTERN.match(first_cell):
            # Yangi guruh bo'limi boshlandi
            current_group = first_cell
            result[current_group] = []
            skip_next_as_header = True

        elif skip_next_as_header:
            # Sarlavha qatori - o'tkazib yuboramiz
            skip_next_as_header = False

        elif current_group is not None:
            # Ma'lumot qatori
            if len(row) >= 6 and row[0] is not None:
                student_id = str(row[0]).strip()
                if not student_id:
                    continue

                try:
                    contract_amount = _to_decimal(row[4])
                    paid_amount = _to_decimal(row[5])
                    course_level = _to_int(row[3], default=1)

                    student_data = {
                        'student_id': student_id,
                        'password': str(row[1]).strip() if row[1] is not None else '',
                        'full_name': str(row[2]).strip() if row[2] is not None else '',
                        'course_level': max(1, min(4, course_level)),
                        'contract_amount': contract_amount,
                        'paid_amount': paid_amount,
                    }
                    result[current_group].append(student_data)
                except Exception:
                    pass  # Noto'g'ri formatdagi qatorlarni o'tkazib yuboramiz

    return result


def _to_decimal(value, default=Decimal('0')):
    if value is None:
        return default
    try:
        return Decimal(str(value).replace(',', '.').strip())
    except InvalidOperation:
        return default


def _to_int(value, default=1):
    if value is None:
        return default
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return default
