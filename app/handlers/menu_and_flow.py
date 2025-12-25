from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.states import GenFlow
from app.keyboards import kb_menu, kb_template, kb_confirm, kb_back_to_menu, kb_cabinet
from app import texts
from app.db import get_or_create_user
from app.services.generation import start_generation

router = Router()

SUPPORT_URL = "https://t.me/your_support"

@router.callback_query(F.data == "continue")
async def on_continue(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer(texts.MENU, reply_markup=kb_menu())
    await call.answer()

@router.callback_query(F.data.in_({"make_reels", "make_neurocard"}))
async def choose_kind(call: CallbackQuery, state: FSMContext):
    kind = "reels" if call.data == "make_reels" else "neurocard"
    await state.update_data(kind=kind)
    await state.set_state(GenFlow.waiting_photo)
    await call.message.answer(texts.ASK_PHOTO, reply_markup=kb_back_to_menu())
    await call.answer()

@router.message(GenFlow.waiting_photo)
async def got_photo(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("Пришли именно фото (не файл).")
        return
    photo_file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=photo_file_id)
    await state.set_state(GenFlow.waiting_product_info)
    await message.answer(texts.ASK_PRODUCT_INFO, reply_markup=kb_back_to_menu())

@router.message(GenFlow.waiting_product_info)
async def got_product_info(message: Message, state: FSMContext):
    # MVP: просто сохраняем текст как product_info.text
    await state.update_data(product_info={"text": message.text})
    await state.set_state(GenFlow.waiting_template)
    await message.answer(texts.CHOOSE_TEMPLATE, reply_markup=kb_template())

@router.callback_query(GenFlow.waiting_template, F.data == "template_1")
async def choose_template(call: CallbackQuery, state: FSMContext):
    await state.update_data(template_id="template_1")
    await state.set_state(GenFlow.waiting_wishes)
    await call.message.answer(texts.ASK_WISHES, reply_markup=kb_back_to_menu())
    await call.answer()

@router.message(GenFlow.waiting_wishes)
async def got_wishes(message: Message, state: FSMContext):
    wishes = message.text.strip()
    if wishes == "-":
        wishes = None
    await state.update_data(extra_wishes=wishes)

    # показать баланс и подтверждение
    user = get_or_create_user(message.from_user.id, message.from_user.username)
    await state.update_data(current_credits=user["credits"])
    await state.set_state(GenFlow.waiting_confirm)

    await message.answer(texts.CONFIRM_COST.format(credits=user["credits"]), reply_markup=kb_confirm())

@router.callback_query(GenFlow.waiting_confirm, F.data == "confirm_generation")
async def confirm_generation(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tg_user_id = call.from_user.id

    # запускаем job + списываем кредит
    try:
        job_id, new_credits = await start_generation(
            bot=call.bot,
            tg_user_id=tg_user_id,
            photo_file_id=data["photo_file_id"],
            kind=data["kind"],
            product_info=data["product_info"],
            extra_wishes=data.get("extra_wishes"),
            template_id=data.get("template_id", "template_1"),
        )
        await call.message.answer(texts.STARTED + f"\n\n💳 Осталось кредитов: {new_credits}")
        await state.clear()
    except Exception as e:
        # если insufficient_credits — можно красиво обработать по тексту
        msg = str(e)
        if "insufficient_credits" in msg:
            await call.message.answer(texts.NO_CREDITS)
        else:
            await call.message.answer(f"❌ Ошибка запуска: {e}")
    await call.answer()

@router.callback_query(F.data == "cancel")
async def cancel_flow(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer(texts.MENU, reply_markup=kb_menu())
    await call.answer()

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer(texts.MENU, reply_markup=kb_menu())
    await call.answer()

@router.callback_query(F.data == "cabinet")
async def cabinet(call: CallbackQuery):
    user = get_or_create_user(call.from_user.id, call.from_user.username)
    await call.message.answer(texts.CABINET.format(credits=user["credits"]), reply_markup=kb_cabinet(SUPPORT_URL))
    await call.answer()

@router.callback_query(F.data == "support")
async def support(call: CallbackQuery):
    await call.message.answer(texts.SUPPORT_TEXT.format(url=SUPPORT_URL))
    await call.answer()

@router.callback_query(F.data == "ref_soon")
async def ref_soon(call: CallbackQuery):
    await call.message.answer("🤝 Реферальная система скоро будет 🙂")
    await call.answer()
