from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.keyboards import kb_menu
from app import texts

router = Router()

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(texts.MENU, reply_markup=kb_menu())

@router.callback_query(F.data.startswith("again:"))
async def again(cb: CallbackQuery):
    # На этом шаге делаем просто: возвращаем в меню,
    # дальше ты нажмёшь “Создать REELS” или “Нейрокарточку”.
    # (Следующим шагом сделаем авто-возврат сразу в нужный флоу)
    await cb.answer("Ок, давай ещё раз")
    await cb.message.answer(texts.MENU, reply_markup=kb_menu())
