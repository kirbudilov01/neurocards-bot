from __future__ import annotations

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.states import GenFlow
from app.keyboards import (
    kb_menu, kb_template, kb_confirm, kb_back_to_menu, kb_cabinet
)
from app import texts
from app.db import get_or_create_user, create_job, consume_credit, supabase
from app.services.tg_files import download_photo_bytes
from app.services.storage import upload_input_photo

import uuid

router = Router()

SUPPORT_URL = "https://t.me/your_support"


# -------------------------
# Helpers
# -------------------------

def _is_active_job_exists(user_id: str) -> bool:
    """Есть ли активная генерация у пользователя (queued/processing)."""
    res = (
        supabase.table("jobs")
        .select("id")
        .eq("user_id", user_id)
        .in_("status", ["queued", "processing"])
        .limit(1)
        .execute()
    )
    return bool(res.data)


async def _start_job_and_charge(
    bot,
    tg_user_id: int,
    username: str | None,
    kind: str,
    photo_file_id: str,
    product_info_text: str,
    extra_wishes: str | None,
    template_id: str = "template_1",
) -> tuple[str, int]:
    """
    1) скачиваем фото
    2) кладём в storage inputs
    3) создаём job
    4) списываем 1 кредит RPC
    """
    # 0) user
    user = get_or_create_user(tg_user_id, username)

    # 1) download photo bytes
    photo_bytes = await download_photo_bytes(bot, photo_file_id)

    # 2) upload to storage
    name = f"{tg_user_id}/{uuid.uuid4().hex}.jpg"
    input_path = f"inputs/{name}"
    upload_input_photo(input_path, photo_bytes)

    # 3) create job
    job = create_job(
        tg_user_id=tg_user_id,
        kind=kind,
        input_photo_path=input_path,
        product_info={"text": product_info_text},
        extra_wishes=extra_wishes,
        template_id=template_id,
    )

    # 4) consume credit
    new_credits = consume_credit(tg_user_id, job["id"])
    return job["id"], new_credits


# -------------------------
# Menu entrypoints
# -------------------------

@router.callback_query(F.data == "continue")
async def on_continue(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer(texts.MENU, reply_markup=kb_menu())
    await call.answer()


@router.callback_query(F.data.in_({"make_reels", "make_neurocard"}))
async def choose_kind(call: CallbackQuery, state: FSMContext):
    kind = "reels" if call.data == "make_reels" else "neurocard"

    # ставим вид генерации и идём в ожидание фото
    await state.update_data(kind=kind)
    await state.set_state(GenFlow.waiting_photo)

    await call.message.answer(texts.ASK_PHOTO, reply_markup=kb_back_to_menu())
    await call.answer()


# -------------------------
# Flow: PHOTO
# -------------------------

@router.message(GenFlow.waiting_photo, F.photo)
async def got_photo(message: Message, state: FSMContext):
    # реальное фото (message.photo) — супер
    photo_file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=photo_file_id)
    await state.set_state(GenFlow.waiting_product_info)
    await message.answer(texts.ASK_PRODUCT_INFO, reply_markup=kb_back_to_menu())


@router.message(GenFlow.waiting_photo)
async def got_not_photo(message: Message, state: FSMContext):
    # сюда упадёт всё, что не photo: document, text, sticker и т.д.
    await message.answer(
        "Нужна именно *фотография* (как Фото, не как Файл).\n"
        "Открой 📎 → *Фото/Видео* → выбери фото товара.\n\n"
        "Если фото с людьми/лицом — лучше сделай снимок без людей 🙂",
        reply_markup=kb_back_to_menu(),
        parse_mode="Markdown",
    )


# -------------------------
# Flow: PRODUCT INFO
# -------------------------

@router.message(GenFlow.waiting_product_info, F.text)
async def got_product_info(message: Message, state: FSMContext):
    await state.update_data(product_info_text=message.text.strip())
    await state.set_state(GenFlow.waiting_template)
    await message.answer(texts.CHOOSE_TEMPLATE, reply_markup=kb_template())


@router.message(GenFlow.waiting_product_info)
async def got_not_text_product_info(message: Message, state: FSMContext):
    await message.answer("Напиши информацию о товаре *текстом* одним сообщением 🙂", parse_mode="Markdown")


# -------------------------
# Flow: TEMPLATE
# -------------------------

@router.callback_query(GenFlow.waiting_template, F.data == "template_1")
async def choose_template(call: CallbackQuery, state: FSMContext):
    await state.update_data(template_id="template_1")
    await state.set_state(GenFlow.waiting_wishes)
    await call.message.answer(texts.ASK_WISHES, reply_markup=kb_back_to_menu())
    await call.answer()


# если нажали что-то другое во время выбора шаблона
@router.callback_query(GenFlow.waiting_template)
async def wrong_template(call: CallbackQuery):
    await call.answer("Выбери Шаблон #1 🙂", show_alert=False)


# -------------------------
# Flow: WISHES
# -------------------------

@router.message(GenFlow.waiting_wishes, F.text)
async def got_wishes(message: Message, state: FSMContext):
    wishes = message.text.strip()
    if wishes == "-":
        wishes = None

    await state.update_data(extra_wishes=wishes)

    user = get_or_create_user(message.from_user.id, message.from_user.username)
    await state.update_data(current_credits=user["credits"])

    await state.set_state(GenFlow.waiting_confirm)
    await message.answer(
        texts.CONFIRM_COST.format(credits=user["credits"]),
        reply_markup=kb_confirm()
    )


@router.message(GenFlow.waiting_wishes)
async def got_not_text_wishes(message: Message):
    await message.answer("Напиши пожелания текстом или отправь `-`", parse_mode="Markdown")


# -------------------------
# Flow: CONFIRM (charge + create job)
# -------------------------

@router.callback_query(GenFlow.waiting_confirm, F.data == "confirm_generation")
async def confirm_generation(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tg_user_id = call.from_user.id
    username = call.from_user.username

    # 0) проверка на параллельные генерации
    user = get_or_create_user(tg_user_id, username)
    if _is_active_job_exists(user["id"]):
        await call.message.answer(
            "⏳ У тебя уже идёт генерация.\n"
            "Подожди 3–5 минут — как будет готово, я пришлю результат.",
            reply_markup=kb_back_to_menu(),
        )
        await call.answer()
        return

    try:
        job_id, new_credits = await _start_job_and_charge(
            bot=call.bot,
            tg_user_id=tg_user_id,
            username=username,
            kind=data["kind"],
            photo_file_id=data["photo_file_id"],
            product_info_text=data["product_info_text"],
            extra_wishes=data.get("extra_wishes"),
            template_id=data.get("template_id", "template_1"),
        )

        await call.message.answer(texts.STARTED + f"\n\n💳 Осталось кредитов: {new_credits}")
        await state.clear()

    except Exception as e:
        msg = str(e)

        if "insufficient_credits" in msg:
            await call.message.answer(texts.NO_CREDITS)
        else:
            await call.message.answer(f"❌ Ошибка запуска генерации: {e}")

    await call.answer()


@router.callback_query(GenFlow.waiting_confirm, F.data == "cancel")
async def cancel_flow(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer(texts.MENU, reply_markup=kb_menu())
    await call.answer()


# -------------------------
# Global menu actions
# -------------------------

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer(texts.MENU, reply_markup=kb_menu())
    await call.answer()


@router.callback_query(F.data == "cabinet")
async def cabinet(call: CallbackQuery):
    user = get_or_create_user(call.from_user.id, call.from_user.username)
    await call.message.answer(
        texts.CABINET.format(credits=user["credits"]),
        reply_markup=kb_cabinet(SUPPORT_URL),
    )
    await call.answer()


@router.callback_query(F.data == "support")
async def support(call: CallbackQuery):
    await call.message.answer(texts.SUPPORT_TEXT.format(url=SUPPORT_URL))
    await call.answer()


@router.callback_query(F.data == "ref_soon")
async def ref_soon(call: CallbackQuery):
    await call.message.answer("🤝 Реферальная система скоро будет 🙂")
    await call.answer()


@router.callback_query(F.data == "cancel")
async def cancel_anywhere(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer(texts.MENU, reply_markup=kb_menu())
    await call.answer()
