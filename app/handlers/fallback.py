from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from app.keyboards import kb_menu
from app import texts

router = Router()

@router.callback_query()
async def unknown_callback(cb: CallbackQuery):
    # Любой неизвестный callback — не молчим
    await cb.answer("Ок, вернул в меню", show_alert=False)
    await cb.message.answer(texts.MENU, reply_markup=kb_menu())

@router.message()
async def unknown_message(message: Message):
    await message.answer(texts.MENU, reply_markup=kb_menu())
