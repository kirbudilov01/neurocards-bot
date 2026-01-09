from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from app import texts
from app.keyboards import (
    kb_menu,
    kb_cabinet,
    kb_back_to_menu,
    kb_confirm,
    kb_no_credits,
    kb_templates,
    kb_topup,     # ✅ ВАЖНО
)
from app.db import get_or_create_user, supabase
from app.services.generation import start_generation

router = Router()

PARSE_MODE = "HTML"
MENU_PHOTO_PATH = "assets/menu.jpg"
MENU_TEXT = getattr(texts, "MENU", "Выберите действие 👇")


async def show_menu(message, text, reply_markup):
    try:
        await message.answer_photo(
            FSInputFile(MENU_PHOTO_PATH),
            caption=text,
            reply_markup=reply_markup,
            parse_mode=PARSE_MODE,
        )
    except Exception:
        await message.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)


def _get_balance(tg_user_id: int) -> int:
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


class GenFlow(StatesGroup):
    waiting_photo = State()
    waiting_product = State()
    waiting_template = State()
    waiting_wishes = State()
    waiting_user_prompt = State()


@router.callback_query(F.data == "continue")
async def on_continue(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    get_or_create_user(cb.from_user.id, cb.from_user.username)
    await show_menu(cb.message, MENU_TEXT, kb_menu())


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await show_menu(cb.message, MENU_TEXT, kb_menu())


@router.callback_query(F.data.startswith("again:"))
async def again(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Ок, ещё раз")
    await state.clear()
    await show_menu(cb.message, MENU_TEXT, kb_menu())


@router.callback_query(F.data == "cabinet")
async def cabinet(cb: CallbackQuery):
    await cb.answer()
    get_or_create_user(cb.from_user.id, cb.from_user.username)
    bal = _get_balance(cb.from_user.id)

    cabinet_tpl = getattr(
        texts,
        "CABINET",
        "👤 <b>Личный кабинет</b>\n\n💳 Баланс: <b>{credits}</b>\n\nВыбери действие:",
    )
    await cb.message.answer(
        cabinet_tpl.format(credits=bal),
        reply_markup=kb_cabinet(),
        parse_mode=PARSE_MODE,
    )


@router.callback_query(F.data == "topup")
async def topup(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(
        getattr(texts, "TOPUP_TEXT", "Пополнение баланса"),
        reply_markup=kb_topup(),
        parse_mode=PARSE_MODE,
    )


@router.callback_query(F.data.startswith("pay:"))
async def pay_stub(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(
        getattr(texts, "PAY_STUB", "Оплата в разработке."),
        reply_markup=kb_cabinet(),
        parse_mode=PARSE_MODE,
    )


@router.callback_query(F.data == "support")
async def support(cb: CallbackQuery):
    await cb.answer()
    txt = getattr(texts, "SUPPORT_TEXT", "🆘 Служба поддержки: {url}")
    await cb.message.answer(
        txt.format(url="https://t.me/your_support"),
        reply_markup=kb_menu(),
        parse_mode=PARSE_MODE,
    )


@router.callback_query(F.data == "make_reels")
async def make_reels(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await state.update_data(kind="reels")
    await state.set_state(GenFlow.waiting_photo)

    await cb.message.answer(
        getattr(texts, "ASK_PHOTO", "Пришли фото товара (без людей в кадре)."),
        reply_markup=kb_back_to_menu(),
        parse_mode=PARSE_MODE,
    )


@router.message(GenFlow.waiting_photo)
async def on_any_image(message: Message, state: FSMContext):
    file_id = None

    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        file_id = message.document.file_id

    if not file_id:
        await message.answer(
            "❌ Пришли именно изображение товара (фото).\n"
            "Можно как фото или как файл, но это должно быть изображение.",
            reply_markup=kb_back_to_menu(),
            parse_mode=PARSE_MODE,
        )
        return

    await state.update_data(photo_file_id=file_id)
    await state.set_state(GenFlow.waiting_product)

    await message.answer(
        getattr(texts, "ASK_PRODUCT_TEXT", "Напиши информацию о товаре одним сообщением."),
        reply_markup=kb_back_to_menu(),
        parse_mode=PARSE_MODE,
    )


@router.message(GenFlow.waiting_product, F.text)
async def on_product_info(message: Message, state: FSMContext):
    await state.update_data(product_text=message.text.strip())
    await state.set_state(GenFlow.waiting_template)

    await message.answer(
        getattr(texts, "CHOOSE_TEMPLATE", "🎛 Выбери шаблон:"),
        reply_markup=kb_templates(),
        parse_mode=PARSE_MODE,
    )


@router.message(GenFlow.waiting_product)
async def on_product_wrong(message: Message):
    await message.answer(
        "Напиши текстом описание товара 🙂",
        reply_markup=kb_back_to_menu(),
        parse_mode=PARSE_MODE,
    )


@router.callback_query(GenFlow.waiting_template, F.data.startswith("tpl:"))
async def on_template(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    template_id = cb.data.split(":", 1)[1]  # ugc/ad/creative/self

    # ✅ страхуемся от мусора
    if template_id not in {"ugc", "ad", "creative", "self"}:
        template_id = "ugc"

    await state.update_data(template_id=template_id)

    if template_id == "self":
        await state.set_state(GenFlow.waiting_user_prompt)
        await cb.message.answer(
            getattr(
                texts,
                "ASK_SELF_PROMPT",
                "🧑‍💻 Вставь свой prompt для Sora/KIE одним сообщением.\n\n"
                "Важно: вертикально 9:16, без текста/субтитров/надписей на видео.",
            ),
            reply_markup=kb_back_to_menu(),
            parse_mode=PARSE_MODE,
        )
        return

    await state.set_state(GenFlow.waiting_wishes)
    await cb.message.answer(
        getattr(texts, "ASK_WISHES", "✨ Есть ли доп. пожелания? Если нет — отправь «-»."),
        reply_markup=kb_back_to_menu(),
        parse_mode=PARSE_MODE,
    )


@router.message(GenFlow.waiting_user_prompt, F.text)
async def on_user_prompt(message: Message, state: FSMContext):
    user_prompt = message.text.strip()
    await state.update_data(user_prompt=user_prompt)

    credits = _get_balance(message.from_user.id)
    confirm_tpl = getattr(
        texts,
        "CONFIRM_COST",
        "Генерация стоит <b>1 кредит</b>.\nТекущий баланс: <b>{credits}</b>\n\nЗапускаем?",
    )
    await message.answer(
        confirm_tpl.format(credits=credits),
        reply_markup=kb_confirm(),
        parse_mode=PARSE_MODE,
    )


@router.message(GenFlow.waiting_wishes, F.text)
async def on_wishes(message: Message, state: FSMContext):
    txt = message.text.strip()
    extra_wishes = None if txt in {"-", "—"} or txt.lower() in {"нет", "no"} else txt
    await state.update_data(extra_wishes=extra_wishes)

    credits = _get_balance(message.from_user.id)
    confirm_tpl = getattr(
        texts,
        "CONFIRM_COST",
        "Генерация стоит <b>1 кредит</b>.\nТекущий баланс: <b>{credits}</b>\n\nЗапускаем?",
    )
    await message.answer(
        confirm_tpl.format(credits=credits),
        reply_markup=kb_confirm(),
        parse_mode=PARSE_MODE,
    )


@router.callback_query(F.data == "confirm_generation")
async def confirm_generation(cb: CallbackQuery, state: FSMContext):
    await cb.answer("Запускаю генерацию 🚀")

    data = await state.get_data()
    photo_file_id = data.get("photo_file_id")
    product_text = (data.get("product_text") or "").strip()
    extra_wishes = data.get("extra_wishes")
    kind = data.get("kind", "reels")
    template_id = data.get("template_id") or "ugc"
    user_prompt = data.get("user_prompt")

    if template_id not in {"ugc", "ad", "creative", "self"}:
        template_id = "ugc"

    if not photo_file_id or not product_text:
        await cb.message.answer(
            "⚠️ Данных не хватает. Начни заново из меню.",
            reply_markup=kb_back_to_menu(),
            parse_mode=PARSE_MODE,
        )
        await state.clear()
        return

    credits = _get_balance(cb.from_user.id)
    if credits < 1:
        await cb.message.answer(
            getattr(texts, "NO_CREDITS", "❌ Недостаточно кредитов. Пополни баланс в личном кабинете."),
            reply_markup=kb_no_credits(),
            parse_mode=PARSE_MODE,
        )
        await state.clear()
        return

    job_id, _new_credits = await start_generation(
        bot=cb.bot,
        tg_user_id=cb.from_user.id,
        idempotency_key=cb.id,
        photo_file_id=photo_file_id,
        kind=kind,
        product_info={"text": product_text, "user_prompt": user_prompt},
        extra_wishes=extra_wishes,
        template_id=template_id,
    )

    await state.clear()
