from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from app.keyboards import kb_menu, kb_cabinet, kb_back_to_menu, kb_confirm
from app import texts
from app.db import get_or_create_user, supabase
from app.services.generation import start_generation

router = Router()

MENU_TEXT = getattr(texts, "MENU", "Выберите действие 👇")


# ---------- CABINET HELPERS ----------
def _get_balance(tg_user_id: int) -> int:
    res = (
        supabase.table("users")
        .select("balance")
        .eq("tg_user_id", tg_user_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        return 0
    return int(res.data[0].get("balance") or 0)


# ---------- REELS FLOW STATES ----------
class ReelsFlow(StatesGroup):
    waiting_photo = State()
    waiting_product = State()
    waiting_wishes = State()


# ---------- MENU BASIC ----------
@router.callback_query(F.data == "continue")
async def on_continue(cb: CallbackQuery):
    await cb.answer()
    get_or_create_user(cb.from_user.id, cb.from_user.username)
    await cb.message.answer(MENU_TEXT, reply_markup=kb_menu())


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await cb.message.answer(MENU_TEXT, reply_markup=kb_menu())


@router.callback_query(F.data.startswith("again:"))
async def again(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Ок, давай ещё одну")
    await state.clear()
    await cb.message.answer(MENU_TEXT, reply_markup=kb_menu())


# ---------- CABINET ----------
@router.callback_query(F.data == "cabinet")
async def cabinet(cb: CallbackQuery):
    await cb.answer()
    u = get_or_create_user(cb.from_user.id, cb.from_user.username)

    bal = _get_balance(cb.from_user.id)

    username = u.get("username") or "-"
    uid = u.get("tg_user_id") or cb.from_user.id

    await cb.message.answer(
        "👤 Личный кабинет\n\n"
        f"🆔 ID: {uid}\n"
        f"👤 Username: @{username}\n"
        f"💳 Баланс: {bal} кредит(ов)\n\n"
        "Если что-то сломалось — пиши в поддержку.",
        reply_markup=kb_cabinet(),
    )
    
@router.callback_query(F.data == "ref_soon")
async def ref_soon(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer("🤝 Реферальная система будет чуть позже. Сейчас допиливаем MVP 🙂", reply_markup=kb_cabinet())
    
@router.callback_query(F.data == "balance")
async def balance(cb: CallbackQuery):
    await cb.answer()
    bal = _get_balance(cb.from_user.id)
    await cb.message.answer(f"💳 Ваш баланс: {bal} кредит(ов)", reply_markup=kb_cabinet())


@router.callback_query(F.data == "support")
async def support(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer("🆘 Поддержка: https://t.me/your_support", reply_markup=kb_menu())


# ---------- REELS START ----------
@router.callback_query(F.data == "make_reels")
async def make_reels(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await state.update_data(kind="reels", template_id="template_1")
    await state.set_state(ReelsFlow.waiting_photo)

    await cb.message.answer(
        "🎬 REELS\n\nПришли фото товара (важно: без людей в кадре).",
        reply_markup=kb_back_to_menu()
    )


# ---------- NEUROCARD (ПОКА СКОРО) ----------
@router.callback_query(F.data == "make_neurocard")
async def make_neurocard(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await state.update_data(kind="neurocard", template_id="template_1")
    await state.set_state(ReelsFlow.waiting_photo)

    await cb.message.answer(
        "🧠 НЕЙРОКАРТОЧКА\n\nПришли фото товара (важно: без людей в кадре).",
        reply_markup=kb_back_to_menu()
    )

# ---------- REELS PHOTO ----------
@router.message(ReelsFlow.waiting_photo, F.photo)
async def reels_photo(message: Message, state: FSMContext):
    photo = message.photo[-1]
    await state.update_data(photo_file_id=photo.file_id)
    await state.set_state(ReelsFlow.waiting_product)

    await message.answer(
        "✍️ Теперь напиши информацию о товаре (коротко: что это, для кого, 2–5 преимуществ).",
        reply_markup=kb_back_to_menu()
    )


@router.message(ReelsFlow.waiting_photo)
async def reels_photo_wrong(message: Message):
    await message.answer(
        "Нужно именно фото товара (картинка). Пришли фото, пожалуйста 🙂",
        reply_markup=kb_back_to_menu()
    )


# ---------- REELS PRODUCT TEXT ----------
@router.message(ReelsFlow.waiting_product, F.text)
async def reels_product(message: Message, state: FSMContext):
    await state.update_data(product_text=message.text.strip())
    await state.set_state(ReelsFlow.waiting_wishes)

    await message.answer(
        "✅ Есть ли доп. пожелания? Например: внешность/манера блогера, настроение.\n\n"
        "Если нет — напиши: нет",
        reply_markup=kb_back_to_menu()
    )


@router.message(ReelsFlow.waiting_product)
async def reels_product_wrong(message: Message):
    await message.answer("Напиши текстом описание товара 🙂", reply_markup=kb_back_to_menu())


# ---------- REELS WISHES ----------
@router.message(ReelsFlow.waiting_wishes, F.text)
async def reels_wishes(message: Message, state: FSMContext):
    txt = message.text.strip()
    extra_wishes = None if txt.lower() in {"нет", "no", "-"} else txt
    await state.update_data(extra_wishes=extra_wishes)

    await message.answer(
        "🚀 Запускаю генерацию. Стоимость: 1 кредит.\nНажми кнопку ниже:",
        reply_markup=kb_confirm()
    )


# ---------- CONFIRM GENERATION ----------
@router.callback_query(F.data == "confirm_generation")
async def confirm_generation(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()

    photo_file_id = data.get("photo_file_id")
    product_text = data.get("product_text", "")
    extra_wishes = data.get("extra_wishes")
    kind = data.get("kind", "reels")
    template_id = data.get("template_id", "template_1")

    if not photo_file_id or not product_text:
        await cb.message.answer(
            "⚠️ Данных не хватает. Начни заново из меню.",
            reply_markup=kb_back_to_menu()
        )
        await state.clear()
        return

    # ВАЖНО: start_generation сам отправляет сообщение (очередь/баланс/кнопки)
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
