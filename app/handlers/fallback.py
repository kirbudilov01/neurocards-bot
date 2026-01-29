from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from app.keyboards import kb_continue, kb_menu
from app import texts
from app.db_adapter import get_or_create_user

router = Router()

WELCOME_VIDEO_PATH = "assets/welcome.mp4"  # положи файл в репу (или закомментируй)
# MENU_PHOTO_PATH = "assets/menu.jpg"

# ✅ /start — ТОЛЬКО текстовая команда
@router.message(CommandStart())
async def start_handler(message: Message):
    get_or_create_user(message.from_user.id, message.from_user.username)

    # 1) видео (если файла нет — закомментируй этот блок)
    try:
        await message.answer_video(FSInputFile(WELCOME_VIDEO_PATH))
    except Exception:
        pass

    # 2) приветствие + кнопка "Продолжить"
    await message.answer(texts.WELCOME, reply_markup=kb_continue(), parse_mode="HTML")


# ✅ неизвестные callback-и — не молчим
@router.callback_query()
async def unknown_callback(cb: CallbackQuery, state: FSMContext):
    # Не вмешиваемся, если есть активный FSM-стейт
    current = await state.get_state()
    if current:
        await cb.answer()
        return
    await cb.answer("Вернул в меню")
    try:
        await cb.message.edit_text(texts.MENU, reply_markup=kb_menu(), parse_mode="HTML")
    except Exception:
        await cb.message.answer(texts.MENU, reply_markup=kb_menu(), parse_mode="HTML")


# ✅ всё остальное — показываем меню (и фото тоже, если вдруг не поймалось state-хендлерами)
@router.message()
async def unknown_message(message: Message, state: FSMContext):
    # Если у пользователя есть активный стейт — не перехватываем сообщение
    current = await state.get_state()
    if current:
        return
    await message.answer(texts.MENU, reply_markup=kb_menu(), parse_mode="HTML")
