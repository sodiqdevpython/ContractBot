from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def parent_main_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="👨‍👩‍👦 Mening farzandlarim")]], resize_keyboard=True)

def student_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Kontrakt holati"), KeyboardButton(text="📝 To'lovlar tarixi")],
            [KeyboardButton(text="👨‍👩‍👦 Ota-onani ulash"), ]
        ],
        resize_keyboard=True
    )

def connect_parent_menu(has_father=False, has_mother=False):
    father_btn = KeyboardButton(text="👨 Ota kiritilgan ✅") if has_father else KeyboardButton(text="👨 Otani ulash")
    mother_btn = KeyboardButton(text="👩 Ona kiritilgan ✅") if has_mother else KeyboardButton(text="👩 Onani ulash")
    
    return ReplyKeyboardMarkup(
        keyboard=[
            [father_btn, mother_btn],
            [KeyboardButton(text="🔙 Bekor qilish")]
        ],
        resize_keyboard=True
    )

def cancel_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Bekor qilish")]], resize_keyboard=True)