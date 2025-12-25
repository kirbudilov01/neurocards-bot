from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from app import texts
from app.keyboards import (
    kb_menu,
    kb_cabinet,
    kb_back_to_menu,
    kb_confirm,
)
from app.db import get_or_create_user, supabase
from app.services.generation import start_generation

router = Router()


# ---------- HELPERS ----------
def _get_balance(tg_user_id: int) -> int:
    """
    Поддержим оба варианта схемы:
    users.balance или users.credits
    """
    res = (
        supabase.table("users")
        .select("*")
        .eq("tg_user_id", tg_user_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        return 0
    row = res.data[0] or {}
    if row.get("balance") is not None:
        return int(row.get("balance") or 0)
    if row.get("credits") is not None:
        return int(row.get("credits") or 0)
    return 0


# ---------- FLOW STATES (общие для reels/neurocard) ----------
class GenFlow(StatesGroup):
    waiting_photo = State()
    waiting_product = State()
    waiting_wishes = State()


# ---------- MENU ----------
@router.callback_query(F.data == "continue")
async def on_continue(cb: CallbackQuery):
    await cb.answer()
    get_or_create_user(cb.from_user.id, cb.from_user.username)
    await cb.message.answer(getattr(texts, "MENU", "Выберите действие 👇"), reply_markup=kb_menu())


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await cb.message.answer(getattr(texts, "MENU", "Выберите действие 👇"), reply_markup=kb_menu())


@router.callback_query(F.data.startswith("again:"))
async def again(cb: CallbackQuery, state: FSMContext):
    # пока просто возвращаем в меню (надёжно)
    await cb.answer("Ок, ещё раз")
    await state.clear()
    await cb.message.answer(getattr(texts, "MENU", "Выберите действие 👇"), reply_markup=kb_menu())


# ---------- CABINET ----------
@router.callback_query(F.data == "cabinet")
async def cabinet(cb: CallbackQuery):
    await cb.answer()
    get_or_create_user(cb.from_user.id, cb.from_user.username)
    bal = _get_balance(cb.from_user.id)

    cabinet_tpl = getattr(texts, "CABINET", "👤 Личный кабинет\nБаланс: {credits}\n\nВыбери действие:")
    await cb.message.answer(
    f"👤 *Личный кабинет*\n\n"
    f"💳 *Баланс:* {bal} кредит(ов)\n\n"
    "Каждая генерация стоит 1 кредит.\n"
    "Пополнение и бонусы — скоро 🚀",
    reply_markup=kb_cabinet(),
    parse_mode="Markdown"
)

@router.callback_query(F.data == "ref_soon")
async def ref_soon(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer("🤝 Реферальная система будет чуть позже 🙂", reply_markup=kb_cabinet())


# ---------- START REELS ----------
@router.callback_query(F.data == "make_reels")
async def make_reels(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await state.update_data(kind="reels", template_id="template_1")
    await state.set_state(GenFlow.waiting_photo)

    await cb.message.answer(
        getattr(texts, "ASK_PHOTO", "Пришли фото товара (без людей в кадре)."),
        reply_markup=kb_back_to_menu(),
    )


# ---------- START NEUROCARD (копия 1-в-1) ----------
@router.callback_query(F.data == "make_neurocard")
async def make_neurocard(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await state.update_data(kind="neurocard", template_id="template_1")
    await state.set_state(GenFlow.waiting_photo)

    await cb.message.answer(
        getattr(texts, "ASK_PHOTO", "Пришли фото товара (без людей в кадре)."),
        reply_markup=kb_back_to_menu(),
    )


# ---------- PHOTO ----------
@router.message(GenFlow.waiting_photo, F.photo)
async def on_photo(message: Message, state: FSMContext):
    photo = message.photo[-1]
    await state.update_data(photo_file_id=photo.file_id)
    await state.set_state(GenFlow.waiting_product)

    await message.answer(
    "✍️ *Напиши информацию о товаре одним сообщением*\n\n"
    "Можешь просто скопировать описание со страницы маркетплейса.\n"
    "Чем больше деталей — тем лучше результат 🚀",
    reply_markup=kb_back_to_menu(),
    parse_mode="Markdown"
)

@router.message(GenFlow.waiting_photo)
async def on_photo_wrong(message: Message):
    await message.answer(
        "Нужно именно фото товара (картинка). Пришли фото, пожалуйста 🙂",
        reply_markup=kb_back_to_menu(),
    )


# ---------- PRODUCT INFO ----------
@router.message(GenFlow.waiting_product, F.text)
async def on_product_info(message: Message, state: FSMContext):
    await state.update_data(product_text=message.text.strip())
    await state.set_state(GenFlow.waiting_wishes)

    await message.answer(
    "✨ *Есть ли доп. пожелания?*\n\n"
    "Например:\n"
    "— внешность человека\n"
    "— стиль видео\n"
    "— настроение\n\n"
    "Если пожеланий нет — отправь «-»",
    reply_markup=kb_back_to_menu(),
    parse_mode="Markdown"
)

@router.message(GenFlow.waiting_product)
async def on_product_wrong(message: Message):
    await message.answer("Напиши текстом описание товара 🙂", reply_markup=kb_back_to_menu())


# ---------- WISHES ----------
@router.message(GenFlow.waiting_wishes, F.text)
async def on_wishes(message: Message, state: FSMContext):
    txt = message.text.strip()
    extra_wishes = None if txt in {"-", "—"} or txt.lower() in {"нет", "no"} else txt
    await state.update_data(extra_wishes=extra_wishes)

    credits = _get_balance(message.from_user.id)
    confirm_tpl = getattr(
        texts,
        "CONFIRM_COST",
        "Генерация стоит 1 кредит.\nТекущий баланс: {credits}\n\nЗапускаем?",
    )
    await message.answer(
        confirm_tpl.format(credits=credits),
        reply_markup=kb_confirm(),
    )


# ---------- CONFIRM ----------
@router.callback_query(F.data == "confirm_generation")
async def confirm_generation(cb: CallbackQuery, state: FSMContext):
    # ВАЖНО: ответить быстро, чтобы не было "query is too old"
    await cb.answer("Запускаю генерацию 🚀")

    data = await state.get_data()
    photo_file_id = data.get("photo_file_id")
    product_text = (data.get("product_text") or "").strip()
    extra_wishes = data.get("extra_wishes")
    kind = data.get("kind", "reels")
    template_id = data.get("template_id", "template_1")

    if not photo_file_id or not product_text:
        await cb.message.answer("⚠️ Данных не хватает. Начни заново из меню.", reply_markup=kb_back_to_menu())
        await state.clear()
        return

    # start_generation сам:
    # - скачает фото
    # - загрузит в storage
    # - создаст job
    # - спишет кредит
    # - отправит пользователю 1 сообщение "генерация запущена" + кнопки
    await start_generation(
        bot=cb.bot,
        tg_user_id=cb.from_user.id,
        photo_file_id=photo_file_id,
        kind=kind,
        product_info={"text": product_text},
        extra_wishes=extra_wishes,
        template_id=template_id,
    )

    await state.clear()


@router.callback_query(F.data == "cancel")
async def cancel(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Ок")
    await state.clear()
    await cb.message.answer(getattr(texts, "MENU", "Выберите действие 👇"), reply_markup=kb_menu())
