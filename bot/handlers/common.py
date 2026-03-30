import base64
from aiogram import Router
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from states.forms import StudentLoginForm, ParentRegistrationForm
from services import api_client
from keyboards.reply import student_main_menu, parent_main_menu, cancel_menu

# Router oldindan ochilgan bo'lishi kerak
router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    
    telegram_id = message.from_user.id
    args = command.args

    # Botga kirgan odam kimligini eng birinchi aniqlaymiz (Aqlli tekshiruv)
    student_data = await api_client.get_student_profile(telegram_id)
    is_student = student_data and student_data.get("success")

    parent_data = await api_client.get_parent_profile(telegram_id)
    is_parent = parent_data and parent_data.get("success")

    # ==========================================
    # 1-HOLAT: Havola orqali kirdi (p_1111_father_U29kaXE)
    # ==========================================
    if args and args.startswith("p_"):
        parts = args.split("_")
        if len(parts) >= 3:
            student_id = parts[1]
            role = parts[2]
            
            # A) O'zining havolasini o'zi bosdimi yoki u talabami?
            if is_student:
                if student_data["student"]["student_id"] == student_id:
                    await message.answer(
                        "⚠️ <b>Diqqat:</b> Siz o'zingizning havolangizni bosdingiz!\n"
                        "Bu havolani faqat ota-onangizga yuborishingiz kerak.", 
                        reply_markup=student_main_menu()
                    )
                else:
                    await message.answer(
                        "⚠️ Tizim xatosi: Siz talaba sifatida ro'yxatdan o'tgansiz, "
                        "boshqa talabaga ota-ona bo'la olmaysiz.", 
                        reply_markup=student_main_menu()
                    )
                return

            # B) Bu ota-ona avval shu farzandga ulanganmi?
            if is_parent:
                linked_students = parent_data.get("linked_students", [])
                already_linked = any(s["student_id"] == student_id and s["status"] == "verified" for s in linked_students)
                if already_linked:
                    await message.answer(
                        "✅ Siz allaqachon bu farzandingizga ulangansiz va tizimda tasdiqlangansiz!", 
                        reply_markup=parent_main_menu()
                    )
                    return

            # V) Oddiy (To'g'ri) holat: Ismni ajratib olib davom etamiz
            student_name = "farzandingiz"
            if len(parts) >= 4:
                try:
                    encoded_name = parts[3]
                    padding = "=" * (4 - len(encoded_name) % 4) if len(encoded_name) % 4 != 0 else ""
                    decoded_name = base64.urlsafe_b64decode(encoded_name + padding).decode('utf-8')
                    student_name = f"<b>{decoded_name}</b>"
                except Exception:
                    pass

            await message.answer(
                f"👋 Assalomu alaykum!\n\n"
                f"Siz {student_name} tomonidan tizimga taklif qilindingiz.\n\n"
                f"Ro'yxatdan o'tish uchun avval <b>Ism-Familiyangizni (F.I.SH)</b> kiriting:",
                reply_markup=cancel_menu()
            )
            
            await state.update_data(student_id=student_id, role=role)
            await state.set_state(ParentRegistrationForm.waiting_for_name)
            return

    # ==========================================
    # 2-HOLAT: Ota-ona oddiy /start bosdi
    # ==========================================
    if is_parent:
        has_verified = any(s['status'] == 'verified' for s in parent_data.get("linked_students", []))
        if has_verified:
            await message.answer(
                "👋 Assalomu alaykum, Hurmatli Ota-ona!\n\n"
                "Pastdagi menyu orqali farzandlaringizning kontrakt holatini kuzatib borishingiz mumkin.", 
                reply_markup=parent_main_menu()
            )
            return

    # ==========================================
    # 3-HOLAT: Talaba oddiy /start bosdi
    # ==========================================
    if is_student:
        student = student_data["student"]
        await message.answer(
            f"🎓 Xush kelibsiz, <b>{student['full_name']}</b>!\n\n"
            f"👇 Quyidagi menyudan kerakli bo'limni tanlang:",
            reply_markup=student_main_menu()
        )
        return

    # ==========================================
    # 4-HOLAT: Hech kim emas -> Login so'raymiz
    # ==========================================
    await message.answer(
        "👋 Assalomu alaykum! Universitetning to'lovlar botiga xush kelibsiz.\n\n"
        "Tizimdan foydalanish uchun <b>Talaba ID</b> raqamingizni yuboring:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(StudentLoginForm.waiting_for_student_id)