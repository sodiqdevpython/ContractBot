import base64
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from states.forms import StudentLoginForm, StudentVerifyOTPForm, StudentConnectionForm
from services import api_client
from keyboards.reply import student_main_menu, connect_parent_menu, cancel_menu, parent_main_menu
from datetime import datetime
from aiogram.exceptions import TelegramBadRequest

router = Router()

# ==========================================
# 1. LOGIN VA PAROL QISMI
# ==========================================
@router.message(StudentLoginForm.waiting_for_student_id)
async def process_student_id(message: Message, state: FSMContext):
    await state.update_data(student_id=message.text.strip())
    await message.answer("🔑 Endi parolingizni kiriting:")
    await state.set_state(StudentLoginForm.waiting_for_password)

@router.message(StudentLoginForm.waiting_for_password)
async def process_password(message: Message, state: FSMContext):
    data = await state.get_data()
    student_id = data.get("student_id")
    password = message.text.strip()

    # RASMNI TELEGRAMDAN QIDIRISH
    photo_url = None
    user_photos = await message.from_user.get_profile_photos()
    if user_photos.total_count > 0:
        best_photo = user_photos.photos[0][-1]
        file_info = await message.bot.get_file(best_photo.file_id)
        photo_url = f"https://api.telegram.org/file/bot{message.bot.token}/{file_info.file_path}"

    tg_data = {
        "telegram_id": message.from_user.id,
        "tg_username": message.from_user.username,
        "tg_first_name": message.from_user.first_name,
        "tg_last_name": message.from_user.last_name,
        "tg_language": message.from_user.language_code,
        "photo_url": photo_url 
    }

    response_data, status_code = await api_client.student_login(student_id, password, tg_data)

    if status_code == 200 and response_data.get("success"):
        student = response_data["student"]
        await state.clear()
        
        await message.answer(
            f"✅ Muvaffaqiyatli tizimga kirdingiz, <b>{student['full_name']}</b>!\n\n"
            f"👇 Pastdagi menyudan kerakli bo'limni tanlang:",
            reply_markup=student_main_menu()
        )
    else:
        await message.answer(
            "❌ Login yoki parol xato!\n\nID raqamingizni qaytadan kiriting:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(StudentLoginForm.waiting_for_student_id)

# ==========================================
# 2. KONTRAKT VA TARIX QISMI
# ==========================================
@router.message(F.text == "📊 Kontrakt holati")
async def show_contract_status(message: Message):
    student_data = await api_client.get_student_profile(message.from_user.id)
    if not student_data or not student_data.get("success"):
        return await message.answer("Tizimda xatolik. Iltimos qayta kiring.")

    student = student_data["student"]
    text = f"🎓 <b>Talaba:</b> {student['full_name']}\n"
    text += f"🏢 <b>Guruh:</b> {student['group']['name'] if student['group'] else 'Biriktirilmagan'}\n"
    text += f"💳 <b>Umumiy kontrakt:</b> {float(student['total_contract_amount']):,.0f} so'm\n"
    text += f"✅ <b>To'langan summa:</b> {float(student['paid_amount']):,.0f} so'm\n"
    text += f"💰 <b>Qoldiq qarz:</b> {float(student['debt_amount']):,.0f} so'm\n"

    await message.answer(text, reply_markup=student_main_menu())

@router.message(F.text == "📝 To'lovlar tarixi")
async def show_payment_history(message: Message):
    student_data = await api_client.get_student_profile(message.from_user.id)
    if not student_data or not student_data.get("success"):
        return await message.answer("Tizimda xatolik. Iltimos qayta kiring.")

    student = student_data["student"]
    payments = student.get('payments', [])
    
    if not payments:
        return await message.answer("🤷‍♂️ Sizda hali to'lovlar tarixi mavjud emas.", reply_markup=student_main_menu())
        
    text = f"📝 <b>{student['full_name']}ning to'lovlar tarixi:</b>\n\n"
    for i, p in enumerate(payments, 1):
        try:
            raw_date = p.get('payment_date', '')
            dt_obj = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
            formatted_date = dt_obj.strftime("%d.%m.%Y %H:%M")
        except:
            formatted_date = p.get('payment_date', "Noma'lum sana")
            
        amount = float(p['amount'])
        text += f"<b>{i}.</b> 💰 <b>{amount:,.0f} so'm</b>\n   📅 Sana: {formatted_date}\n   🎓 O'quv yili: {p.get('academic_year', '')}\n\n"

    text += f"<b>Jami to'langan:</b> {float(student['paid_amount']):,.0f} so'm"
    await message.answer(text, reply_markup=student_main_menu())

# ==========================================
# 3. OTA-ONANI ULASH VA TASDIQLASH QISMI
# ==========================================
@router.message(F.text == "🔙 Bekor qilish")
async def cancel_any_action(message: Message, state: FSMContext):
    current_state = await state.get_state()
    await state.clear()

    # 1. Agar foydalanuvchi Ota-ona ro'yxatidan o'tish jarayonida bo'lsa
    if current_state and current_state.startswith("ParentRegistrationForm"):
        
        # Bu odamning oldindan ota-ona sifatida profili bor-yo'qligini tekshiramiz
        parent_res = await api_client.get_parent_profile(message.from_user.id)
        if parent_res and parent_res.get("success") and parent_res.get("linked_students"):
            # Agar oldin ulangan farzandi bo'lsa, Ota-ona menyusiga qaytaramiz
            await message.answer("❌ Jarayon bekor qilindi.", reply_markup=parent_main_menu())
        else:
            # Agar butunlay yangi foydalanuvchi bo'lsa, klaviaturani tozalaymiz
            await message.answer(
                "❌ Ro'yxatdan o'tish bekor qilindi.\n\nQaytadan boshlash uchun farzandingiz yuborgan havolani yana bir bor bosing.", 
                reply_markup=ReplyKeyboardRemove()
            )
    
    # 2. Qolgan barcha holatlarda (Talaba uchun)
    else:
        await message.answer("❌ Jarayon bekor qilindi.", reply_markup=student_main_menu())


@router.message(F.text == "👨‍👩‍👦 Ota-onani ulash")
async def connect_parent_menu_handler(message: Message):
    student_data = await api_client.get_student_profile(message.from_user.id)
    if not student_data or not student_data.get("success"):
        return await message.answer("Tizimda xatolik yuz berdi. /start ni bosing.")

    parents = student_data["student"].get("parents", [])
    text = "👨‍👩‍👦 <b>Ota-ona boshqaruvi</b>\n\n"
    
    has_father = False
    has_mother = False
    verified_parents = []
    pending_parents = []
    
    # Otasi yoki onasi borligini aniqlash
    for p in parents:
        if p['role'] == 'father':
            has_father = True
        elif p['role'] == 'mother':
            has_mother = True
            
        if p['status'] == 'verified':
            verified_parents.append(p)
        else:
            pending_parents.append(p)
            
    if verified_parents:
        text += "✅ <b>Ulanganlar:</b>\n"
        for p in verified_parents:
            text += f"🔹 {p['role_display']}: {p['parent']['full_name']} ({p['parent']['phone_number']})\n"
        text += "\n"
        
    if pending_parents:
        text += "⏳ <b>Kutilayotganlar:</b>\n"
        for p in pending_parents:
            name = p['parent'].get('full_name') or "Ism kiritilmagan"
            text += f"🔹 {p['role_display']}: {name} ({p['parent']['phone_number']})\n"
        text += "\n"
        
    text += "Kimni tizimga ulamoqchisiz? Pastki menyudan tanlang:\n"
    
    # Dinamik menyuni chaqiramiz
    from keyboards.reply import connect_parent_menu
    await message.answer(text, reply_markup=connect_parent_menu(has_father, has_mother))

@router.message(F.text.in_(["👨 Otani ulash", "👩 Onani ulash", "👨 Ota kiritilgan ✅", "👩 Ona kiritilgan ✅"]))
async def generate_standard_link(message: Message):
    if "kiritilgan ✅" in message.text:
        return await message.answer(
            "⚠️ <b>Diqqat:</b> Siz ushbu shaxsni allaqachon kiritgansiz!\n\n"
            "Agar xatolik bilan boshqa raqam kiritgan bo'lsangiz yoki o'zgartirmoqchi bo'lsangiz, "
            "iltimos guruh tyutoriga murojaat qiling."
        )

    role = "father" if "Ota" in message.text else "mother"
    student_data = await api_client.get_student_profile(message.from_user.id)
    
    student_id = student_data["student"]["student_id"]
    full_name = student_data["student"]["full_name"]
    
    # Telegram linklari qisqa bo'lishi kerak, shuning ismni qisqartirib (maksimum 30 harf) base64 ga o'giramiz
    safe_name = full_name[:30]
    encoded_name = base64.urlsafe_b64encode(safe_name.encode('utf-8')).decode('utf-8').rstrip('=')
    
    bot_info = await message.bot.get_me()
    # Endi havolaga encoded_name ni ham qo'shib yuboramiz
    link = f"https://t.me/{bot_info.username}?start=p_{student_id}_{role}_{encoded_name}"
    
    from keyboards.reply import student_main_menu
    await message.answer(
        f"✅ <b>Havola tayyorlandi!</b>\n\n"
        f"Quyidagi havolani yuboring:\n🔗 <b>{link}</b>\n\n"
        f"<i>Ular kirib ro'yxatdan o'tgach, sizga bildirishnoma keladi.</i>",
        reply_markup=student_main_menu()
    )

@router.callback_query(F.data.startswith("cancel_"))
async def handle_cancel_pending(call: CallbackQuery):
    sp_id = call.data.split("_")[1]
    await api_client.cancel_pending(sp_id)
    await call.message.edit_text("❌ Ushbu so'rov o'chirib yuborildi.")

@router.callback_query(F.data.startswith("trigger_otp_"))
async def send_otp_to_parent(call: CallbackQuery, state: FSMContext):
    sp_id = call.data.split("_")[2]
    res = await api_client.trigger_otp(sp_id)
    
    if res.get("success"):
        ikb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Qayta yuborish", callback_data=f"trigger_otp_{sp_id}")]
        ])
        
        try:
            # Agar xabar oldin ham shunday bo'lsa xato bermasligi uchun try-except
            await call.message.edit_text(
                "✅ <b>Kod yuborildi!</b>\n\nOta-onangizga borgan 6 xonali kodni so'rab, shu yerga yozib yuboring:",
                reply_markup=ikb
            )
        except TelegramBadRequest:
            pass # Xabar o'zgarmagan bo'lsa, indamaymiz
            
        # Foydalanuvchi tugma ishlaganini bilishi uchun tepadan pop-up chiqaramiz
        await call.answer("✅ Yangi kod ota-onangizga yuborildi!", show_alert=True)
        
        await state.update_data(current_sp_id=sp_id)
        await state.set_state(StudentConnectionForm.waiting_for_specific_otp)

@router.message(StudentConnectionForm.waiting_for_specific_otp)
async def submit_otp_final(message: Message, state: FSMContext):
    otp_code = message.text.strip()
    data = await state.get_data()
    sp_id = data.get("current_sp_id")
    
    res, status_code = await api_client.verify_otp_by_sp(sp_id, otp_code)
    
    if status_code == 200 and res.get("success"):
        # 1. Talabaga muvaffaqiyat xabarini beramiz
        await message.answer("✅ Muvaffaqiyatli! Ota-ona tizimga ulandi.", reply_markup=student_main_menu())
        await state.clear()
        
        # 2. Ota-onaga tabriknoma va MENYU (Tugmalar) yuboramiz
        parent_tg_id = res.get("parent_tg_id")
        student_name = res.get("student_name")
        
        if parent_tg_id:
            parent_text = (
                f"✅ <b>Tabriklaymiz!</b>\n\n"
                f"Siz <b>{student_name}</b> ning tizimiga muvaffaqiyatli ulandingiz!\n\n"
                f"Pastdagi menyu orqali farzandingizning kontrakt holatini kuzatib borishingiz mumkin."
            )
            # Bot to'g'ridan-to'g'ri ota-onaga yozadi
            await message.bot.send_message(
                chat_id=parent_tg_id, 
                text=parent_text, 
                reply_markup=parent_main_menu()
            )
            
    else:
        ikb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Qayta yuborish", callback_data=f"trigger_otp_{sp_id}")]])
        await message.answer("❌ Xato kod. Boshqatdan urinib ko'ring yoki qayta yuboring.", reply_markup=ikb)