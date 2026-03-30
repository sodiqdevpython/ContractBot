from aiogram.fsm.state import State, StatesGroup

class StudentLoginForm(StatesGroup):
    waiting_for_student_id = State()
    waiting_for_password = State()

class ParentRegistrationForm(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()

class StudentVerifyOTPForm(StatesGroup):
    waiting_for_otp = State()

class StudentConnectionForm(StatesGroup):
    waiting_for_custom_role = State()
    waiting_for_specific_otp = State()