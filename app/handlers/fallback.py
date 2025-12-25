from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.keyboards import kb_menu
from app import texts

router = Router()


@router.callback_query()
async def unknown_callback(cb: CallbackQuery, state: FSMContext):
    """
    Любой неизвестный callback:
    — аккуратно сбрасываем FSM
    — возвращаем пользователя в меню
    """
    await cb.answer("Вернул в меню")
    await state.clear()

    await cb.message.answer(
        texts.MENU,
        reply_markup=kb_menu(),
        parse_mode="HTML",
    )


@router.message()
async def unknown_message(message: Message, state: FSMContext):
    """
    Любое сообщение вне сценария:
    — НЕ ловит фото (их ловят хендлеры выше)
    — безопасно возвращает в меню
    """
    await state.clear()

    await message.answer(
        texts.MENU,
        reply_markup=kb_menu(),
        parse_mode="HTML",
    )
