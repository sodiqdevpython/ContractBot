# ContractBot — Alfraganus University

Talabalarning kontrakt va to'lovlarini kuzatib boruvchi tizim.  
**Telegram bot** + **Tutor/Admin web panel** + **Celery xabarnomalar**.

---

## Texnologik stek

| Qism | Texnologiya |
|---|---|
| Backend | Python 3.x, Django 4.x, DRF |
| Bot | Aiogram 3.x (asinxron) |
| Fon vazifalari | Celery + Redis |
| Excel | openpyxl |
| DB | PostgreSQL (Docker) |
| UI | Bootstrap 5, FontAwesome 6 |

---

## Ishga tushirish

```bash
# Docker bilan (tavsiya etiladi)
docker-compose up --build

# Migratsiyalar
docker-compose exec web python manage.py migrate

# Superuser yaratish
docker-compose exec web python manage.py createsuperuser
```

---

## URL manzillar

| URL | Tavsif |
|---|---|
| `/admin/` | Django admin paneli |
| `/dashboard/login/` | Tutor/Admin kirish sahifasi |
| `/dashboard/` | Guruhlar ro'yxati |
| `/dashboard/groups/<id>/` | Guruh tafsiloti (talabalar jadvali) |
| `/dashboard/students/<id>/` | Talaba tafsiloti |
| `/dashboard/excel-import/` | Excel fayl yuklash |
| `/dashboard/admin-overview/` | Admin umumiy statistika |

---

## Rollar

### Admin (`is_staff=True`)
- Barcha guruhlarni ko'rish
- Umumiy statistika sahifasi
- Istalgan talabaga kirish
- Excel import (barcha guruhlar)

### Tutor (oddiy foydalanuvchi)
- Faqat o'ziga biriktirilgan guruhlarni ko'radi
- Talabalar to'lovini tasdiqlash
- Excel import (faqat o'z guruhlari)

---

## Ma'lumotlar bazasi modellari

```
Group          → tutor (User FK)
Student        → group (Group FK)
StudentContract → student, academic_year, contract_amount, paid_amount
Payment        → contract (StudentContract FK)
Parent         → phone_number (unique)
StudentParent  → student + parent (M2M ko'prigi), OTP tasdiqlash
NotificationCampaign → guruh + filtr + xabar
ExcelImport    → fayl yuklash tarixi
TutorPaymentConfirmation → contract, tutor, is_active (dashboard app)
```

---

## Excel fayl formati

Bir faylda bir nechta guruh bo'lishi mumkin:

```
ki-23-1                         ← guruh nomi (kichik harf, A ustun)
1       2      3      4    5         6
login   parol  ism    kurs kontrakt  to'landi
s001    pass1  Ali V  1    5000000   2500000
s002    pass2  Vali A 1    5000000   0
                                    ← bo'sh qator (ixtiyoriy)
ki-23-2
1       2      ...
```

**Guruh nomi formati:** `[2 harf]-[2 raqam]-[1-2 raqam]` → masalan `ki-23-1`, `cs-24-12`

---

## To'lov tasdiqlash mantig'i

```
Talaba to'ladi (Excel kelmagan)
    ↓
Tutor tizimga kirib "To'laganini tasdiqlash" bosadi
    ↓
TutorPaymentConfirmation yaratiladi (is_active=True)
    ↓
Xabarnomalar TO'XTATILADI
    ↓
Excel import keladi → paid_amount yangilanadi
    ↓
TutorPaymentConfirmation bekor qilinadi (is_active=False)
    ↓
Agar hali qarz bo'lsa → Xabarnomalar QAYTA BOSHLANADI
Agar to'liq bo'lsa → Xabarnomalar o'z-o'zidan to'xtaydi
```

---

## Telegram bot oqimi

### Talaba
1. `/start` → ID kiritadi → parol kiritadi → avtorizatsiya
2. Kontrakt holati, to'lov tarixi ko'radi
3. Ota-onaga Deep Link yaratadi (Base64 encoded)

### Ota-ona
1. Talaba yuborgan havolani bosadi
2. Ism va telefon raqam kiritadi
3. Talabaning botiga OTP yuboriladi
4. Talaba kodni tasdiqlaydi → `verified` status
5. "Mening farzandlarim" menyusidan barcha farzandlarini ko'radi

---

## Xabarnomalar (Celery Beat)

`NotificationCampaign` modeli orqali:
- Guruh bo'yicha filtr
- Grant/Kontrakt bo'yicha filtr
- Qarz foizi bo'yicha filtr (25%, 50%, 75%, 100%)
- Kunlik ma'lum vaqtda yuboriladi

**Xabarnoma TO'XTATILADI agar:**
- Talabaning aktiv `TutorPaymentConfirmation` si mavjud bo'lsa
- Yoki `paid_amount >= contract_amount` bo'lsa

---

## Ishlab chiqish jarayoni

### Tugallangan ✅
- [x] Ma'lumotlar bazasi arxitekturasi (models.py)
- [x] REST API (views.py, serializers.py)
- [x] Telegram bot (aiogram 3.x)
- [x] Celery xabarnomalar (tasks.py)
- [x] Django admin paneli (LockableAdmin, 24 soatlik qulf)
- [x] **Web UI** (Tutor va Admin dashboard)
  - [x] Login/Logout sahifasi
  - [x] Guruhlar ro'yxati (statistika bilan)
  - [x] Guruh tafsiloti (qidiruv, filter, qarz holati)
  - [x] Talaba tafsiloti (kontraktlar, to'lovlar, tasdiq)
  - [x] Excel import (ko'p guruhli format)
  - [x] Admin umumiy statistika
- [x] TutorPaymentConfirmation modeli va mantig'i

### Rejadagi 🔜
- [ ] Notification kampaniya UI (web paneldan boshqarish)
- [ ] To'lov qo'shish UI (tutor tomonidan)
- [ ] Excel eksport (guruh bo'yicha hisobot)
- [ ] Talabalar uchun API autentifikatsiya (JWT)
