import aiohttp
from config import BASE_API_URL

async def get_student_profile(telegram_id: int):
    """Telegram ID orqali talabani bazadan qidiradi"""
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_API_URL}/student/profile/{telegram_id}/"
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            return None

async def get_parent_profile(telegram_id: int):
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_API_URL}/parent/profile/{telegram_id}/"
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            return {"success": False}

async def student_login(student_id: str, password: str, telegram_data: dict):
    """Talaba ID va paroli orqali tizimga kirish (va Telegram ID ni bog'lash)"""
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_API_URL}/student/login/"
        payload = {
            "student_id": student_id,
            "password": password,
            **telegram_data # Telegram ma'lumotlarini qo'shib yuboramiz
        }
        try:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    return await response.json(), 200
                return await response.json(), response.status
        except Exception as e:
            return {"success": False, "message": str(e)}, 500

async def register_parent(student_id: str, phone_number: str, telegram_data: dict):
    """Ota-onani ro'yxatdan o'tkazish va OTP olish"""
    async with aiohttp.ClientSession() as session:
        # Django urls.py dagi yo'lga moslang (masalan: /parent/register/)
        url = f"{BASE_API_URL}/parent/register/"
        payload = {
            "student_id": student_id,
            "phone_number": phone_number,
            **telegram_data
        }
        try:
            async with session.post(url, json=payload) as response:
                return await response.json(), response.status
        except Exception as e:
            return {"success": False, "message": str(e)}, 500

async def verify_otp(student_id: str, otp_code: str):
    """Talaba tomonidan OTP kodni tasdiqlash"""
    async with aiohttp.ClientSession() as session:
        # Django urls.py dagi yo'lga moslang
        url = f"{BASE_API_URL}/parent/verify-otp/"
        payload = {
            "student_id": student_id,
            "otp_code": otp_code
        }
        try:
            async with session.post(url, json=payload) as response:
                return await response.json(), response.status
        except Exception as e:
            return {"success": False, "message": str(e)}, 500


async def get_pending_parents(student_id: str):
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_API_URL}/parent/pending/{student_id}/"
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            return {"success": False}

async def resend_otp(sp_id: int):
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_API_URL}/parent/resend-otp/"
        async with session.post(url, json={"sp_id": sp_id}) as response:
            return await response.json()

async def cancel_pending(sp_id: int):
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_API_URL}/parent/cancel-pending/"
        async with session.post(url, json={"sp_id": sp_id}) as response:
            return await response.json()

async def register_parent_init(student_id, phone, name, role, custom_role, tg_data):
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_API_URL}/parent/init-register/"
        payload = {"student_id": student_id, "phone_number": phone, "full_name": name, "role": role, "custom_role_name": custom_role, **tg_data}
        async with session.post(url, json=payload) as response:
            return await response.json(), response.status

async def trigger_otp(sp_id):
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_API_URL}/parent/trigger-otp/"
        async with session.post(url, json={"sp_id": sp_id}) as response:
            return await response.json()

async def verify_otp_by_sp(sp_id, otp_code):
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_API_URL}/parent/verify-otp/"
        async with session.post(url, json={"sp_id": sp_id, "otp_code": otp_code}) as response:
            return await response.json(), response.status