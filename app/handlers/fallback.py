from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.keyboards import kb_menu
from app import texts

router = Router()

@router.message()
async def fallback_handler(message: Message, state: FSMContext):
    cur = await state.get_state()
    if cur is None:
        await message.answer(texts.MENU, reply_markup=kb_menu())
