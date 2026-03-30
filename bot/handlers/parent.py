import re
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, CallbackQuery
from aiogram.fsm.context import FSMContext
from states.forms import ParentRegistrationForm
from services import api_client
from keyboards.reply import parent_main_menu
from datetime import datetime

router = Router()

@router.message(ParentRegistrationForm.waiting_for_name)
async def process_parent_name(message: Message, state: FSMContext):
    full_name = message.text.strip()
    await state.update_data(full_name=full_name)
    
    contact_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)],
            [KeyboardButton(text="🔙 Bekor qilish")]
        ], resize_keyboard=True
    )
    
    await message.answer(
        f"Rahmat, <b>{full_name}</b>!\n\n"
        f"Endi telefon raqamingizni kiriting:",
        reply_markup=contact_kb
    )
    await state.set_state(ParentRegistrationForm.waiting_for_phone)

@router.message(ParentRegistrationForm.waiting_for_phone)
async def process_parent_phone(message: Message, state: FSMContext):
    phone_number = message.contact.phone_number if message.contact else message.text.strip()
    if not phone_number.startswith("+"): 
        phone_number = "+" + phone_number

    # YANGILANGAN QAT'IY VALIDATSIYA (Xalqaro format)
    if not re.match(r"^\+\d{7,15}$", phone_number):
        return await message.answer("❌ Noto'g'ri format! Iltimos, raqamni to'g'ri xalqaro formatda kiriting (Masalan: +998901234567 yoki +79... ).")

    data = await state.get_data()
    tg_data = {"telegram_id": message.from_user.id, "tg_username": message.from_user.username, "tg_first_name": message.from_user.first_name}

    res, status = await api_client.register_parent_init(
        data.get("student_id"), phone_number, data.get("full_name"), 
        data.get("role"), "", tg_data # custom_role_name endi bo'm-bo'sh yuboriladi
    )

    if status == 200 and res.get("success"):
        await message.answer("⏳ <b>Kuting...</b>\n\nMa'lumotlaringiz farzandingizga yuborildi. U tasdiqlash uchun sizga kod jo'natadi.", reply_markup=ReplyKeyboardRemove())
        await state.clear()
        
        # TALABAGA XABAR VA TUGMA YUBORISH
        sp_id = res.get("sp_id")
        ikb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📨 Kodni yuborish", callback_data=f"trigger_otp_{sp_id}")]
        ])
        await message.bot.send_message(
            chat_id=res.get("student_tg_id"),
            text=f"🔔 <b>Yangi ulanish!</b>\n\nSiz yuborgan havola orqali <b>{data.get('full_name')}</b> ({res.get('role_display')}) ro'yxatdan o'tdi.\n\nTasdiqlash kodini yuborish uchun pastdagi tugmani bosing:",
            reply_markup=ikb
        )
    else:
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")


# --- OTA-ONA FARZANDLARI RO'YXATINI KO'RISHI ---
@router.message(F.text == "👨‍👩‍👦 Mening farzandlarim")
async def show_my_children(message: Message):
    res = await api_client.get_parent_profile(message.from_user.id)
    if not res or not res.get("success"):
        return await message.answer("Siz hali tizimda tasdiqlanmagansiz.")
        
    students = res.get("linked_students", [])
    if not students:
        return await message.answer("Sizga ulangan farzandlar topilmadi.")
        
    # Har bir farzand uchun alohida karta shaklida yuborish
    for st in students:
        text = f"🎓 <b>Talaba:</b> {st['student_name']}\n"
        text += f"🏢 <b>Guruh:</b> {st['group_name']}\n"
        text += f"💳 <b>Umumiy kontrakt:</b> {float(st['total_contract_amount']):,.0f} so'm\n"
        text += f"✅ <b>To'langan summa:</b> {float(st['paid_amount']):,.0f} so'm\n"
        text += f"💰 <b>Qoldiq qarz:</b> {float(st['debt_amount']):,.0f} so'm\n"
        
        ikb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 To'lovlar tarixi", callback_data=f"phistory_{st['student_id']}")]
        ])
        await message.answer(text, reply_markup=ikb)

# --- OTA-ONA ALOHIDA FARZAND TARIXINI KO'RISHI ---
@router.callback_query(F.data.startswith("phistory_"))
async def show_parent_child_history(call: CallbackQuery):
    student_id = call.data.split("_")[1]
    res = await api_client.get_parent_profile(call.from_user.id)
    
    if not res or not res.get("success"):
        return await call.answer("Xatolik yuz berdi", show_alert=True)
        
    student = next((s for s in res["linked_students"] if s["student_id"] == student_id), None)
    if not student:
        return await call.answer("Talaba topilmadi", show_alert=True)
        
    payments = student.get("payments", [])
    if not payments:
        return await call.message.answer(f"🤷‍♂️ <b>{student['student_name']}</b> da hali to'lovlar tarixi yo'q.")
        
    text = f"📝 <b>{student['student_name']}ning to'lovlar tarixi:</b>\n\n"
    
    for i, p in enumerate(payments, 1):
        try:
            raw_date = p.get('payment_date', '')
            if raw_date:
                dt_obj = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
                formatted_date = dt_obj.strftime("%d.%m.%Y")
            else:
                formatted_date = "Noma'lum"
        except:
            formatted_date = "Noma'lum sana"
            
        amount = float(p['amount'])
        text += f"<b>{i}.</b> 💰 <b>{amount:,.0f} so'm</b>\n   📅 Sana: {formatted_date}\n   🎓 O'quv yili: {p.get('academic_year', '')}\n\n"
        
    await call.message.answer(text)
    await call.answer()