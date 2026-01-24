import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from app import texts
from app.states import GenFlow  # ✅ Импортируем из states
from app.keyboards import (
    kb_menu,
    kb_cabinet,
    kb_back_to_menu,
    kb_confirm,
    kb_no_credits,
    kb_templates,
    kb_topup,     # ✅ ВАЖНО
    kb_video_count,  # ✅ Новая клавиатура
)
from app.db_adapter import get_or_create_user, safe_get_balance, get_user_jobs
from app.services.generation import start_generation
from app.utils import ensure_dict

router = Router()

PARSE_MODE = "HTML"
MENU_PHOTO_PATH = "/app/assets/menu.jpg"
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


@router.callback_query(F.data == "continue")
async def on_continue(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await get_or_create_user(cb.from_user.id, cb.from_user.username)
    await show_menu(cb.message, MENU_TEXT, kb_menu())


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await show_menu(cb.message, MENU_TEXT, kb_menu())


# ❌ ОТКЛЮЧЕНО: Кнопка "Сделать еще видео" не работает, так как file_id картинки устаревает
# Пользователь должен загрузить картинку заново через обычный флоу
#
# @router.callback_query(F.data.startswith("again:"))
# async def again(cb: CallbackQuery, state: FSMContext, bot: Bot):
#     """Повторная генерация видео с теми же параметрами"""
#     await cb.answer("⚠️ Эта функция временно недоступна. Пожалуйста, загрузите фото заново.")
#     await cb.message.answer(
#         "⚠️ Функция повтора временно недоступна.\n\nПожалуйста, загрузите фото заново для новой генерации.",
#         reply_markup=kb_back_to_menu(),
#         parse_mode=PARSE_MODE,
#     )


@router.callback_query(F.data == "cabinet")
async def cabinet(cb: CallbackQuery):
    try:
        await cb.answer()
        await get_or_create_user(cb.from_user.id, cb.from_user.username)
        bal = await safe_get_balance(cb.from_user.id)

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
    except Exception as e:
        logging.error(f"Error in cabinet: {e}", exc_info=True)
        await cb.message.answer(
            "⚠️ Ошибка, попробуй ещё раз",
            reply_markup=kb_back_to_menu(),
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


# @router.callback_query(F.data == "support")  
# async def support(cb: CallbackQuery):
#     # Удалён - теперь кнопка поддержки это URL кнопка (https://t.me/fabricbothelper)
#     pass


@router.callback_query(F.data == "make_reels")
async def make_reels(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await state.update_data(kind="reels")
    await state.set_state(GenFlow.waiting_photo)

    # ✅ Show user their current balance
    balance = await safe_get_balance(cb.from_user.id)
    ask_photo_text = getattr(texts, "ASK_PHOTO", "Пришли фото товара (без людей в кадре).")
    
    full_text = (
        f"{ask_photo_text}\n\n"
        f"💳 <b>Ваш баланс: {balance} {'кредит' if balance == 1 else 'кредитов'}</b>\n"
        f"<i>Каждое видео стоит 1 кредит</i>"
    )

    await cb.message.answer(
        full_text,
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
    await state.set_state(GenFlow.waiting_product_info)

    await message.answer(
        getattr(texts, "ASK_PRODUCT_TEXT", "Напиши информацию о товаре одним сообщением."),
        reply_markup=kb_back_to_menu(),
        parse_mode=PARSE_MODE,
    )


@router.message(GenFlow.waiting_product_info, F.text)
async def on_product_info(message: Message, state: FSMContext):
    await state.update_data(product_text=message.text.strip())
    await state.set_state(GenFlow.waiting_template)

    await message.answer(
        getattr(texts, "CHOOSE_TEMPLATE", "🎛 Выбери шаблон:"),
        reply_markup=kb_templates(),
        parse_mode=PARSE_MODE,
    )


@router.message(GenFlow.waiting_product_info)
async def on_product_wrong(message: Message):
    await message.answer(
        "Напиши текстом описание товара 🙂",
        reply_markup=kb_back_to_menu(),
        parse_mode=PARSE_MODE,
    )


@router.callback_query(GenFlow.waiting_template, F.data.startswith("tpl:"))
async def on_template(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    template_id = cb.data.split(":", 1)[1]  # ugc/ad/self

    # ✅ страхуемся от мусора и удаленного creative
    if template_id not in {"ugc", "ad", "self"}:
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
    try:
        user_prompt = message.text.strip()
        await state.update_data(user_prompt=user_prompt)
        await state.set_state(GenFlow.waiting_video_count)

        await message.answer(
            "🎬 <b>Сколько видео хочешь сгенерировать?</b>\n\n"
            "Каждое видео = 1 кредит",
            reply_markup=kb_video_count(),
            parse_mode=PARSE_MODE,
        )
    except Exception as e:
        logging.error(f"Error in on_user_prompt: {e}", exc_info=True)
        await message.answer(
            "⚠️ Ошибка, попробуй ещё раз",
            reply_markup=kb_back_to_menu(),
            parse_mode=PARSE_MODE,
        )


@router.message(GenFlow.waiting_wishes, F.text)
async def on_wishes(message: Message, state: FSMContext):
    try:
        txt = message.text.strip()
        txt_lower = txt.lower()
        if txt_lower in {"-", "—", "нет", "no"} or " нет" in f" {txt_lower} ":
            extra_wishes = None
        else:
            extra_wishes = txt
        await state.update_data(extra_wishes=extra_wishes)

        # Переход к выбору количества видео
        await state.set_state(GenFlow.waiting_video_count)
        await message.answer(
            "📊 <b>Сколько видео сделать?</b>\n\n"
            "Выберите количество:",
            reply_markup=kb_video_count(),
            parse_mode=PARSE_MODE,
        )
    except Exception as e:
        logging.error(
            f"Error in on_wishes for user {message.from_user.id} with text='{message.text}': {e}",
            exc_info=True,
        )
        await message.answer(
            "⚠️ Ошибка, попробуй ещё раз или отправь ‘-’",
            reply_markup=kb_back_to_menu(),
            parse_mode=PARSE_MODE,
        )

# Новый обработчик выбора количества видео
@router.callback_query(GenFlow.waiting_video_count, F.data.startswith("count:"))
async def on_video_count(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    count = int(cb.data.split(":", 1)[1])  # 1, 3, or 5
    await state.update_data(video_count=count)

    credits = await safe_get_balance(cb.from_user.id)
    if credits < count:
        await cb.message.answer(
            f"❌ Недостаточно кредитов.\n\nНужно: <b>{count}</b>\nУ вас: <b>{credits}</b>\n\nПополните баланс.",
            reply_markup=kb_no_credits(),
            parse_mode=PARSE_MODE,
        )
        await state.clear()
        return

    confirm_tpl = (
        f"🎬 <b>Готовы запустить генерацию?</b>\n\n"
        f"Количество видео: <b>{count}</b>\n"
        f"Стоимость: <b>{count} {'кредит' if count == 1 else 'кредита' if count < 5 else 'кредитов'}</b>\n"
        f"Текущий баланс: <b>{credits}</b>\n\n"
        f"⏱ Генерация займёт от <b>1 до 30 минут</b> в зависимости от загруженности нейросети Sora 2.\n\n"
        f"Запускаем?"
    )
    
    await cb.message.answer(
        confirm_tpl,
        reply_markup=kb_confirm(count),
        parse_mode=PARSE_MODE,
    )

@router.callback_query(F.data == "confirm_generation")
async def confirm_generation(cb: CallbackQuery, state: FSMContext):
    await cb.answer()

    try:
        data = await state.get_data()
        photo_file_id = data.get("photo_file_id")
        product_text = (data.get("product_text") or "").strip()
        extra_wishes = data.get("extra_wishes")
        kind = data.get("kind", "reels")
        template_id = data.get("template_id") or "ugc"
        user_prompt = data.get("user_prompt")
        video_count = data.get("video_count", 1)

        if template_id not in {"ugc", "ad", "self"}:
            template_id = "ugc"

        if not photo_file_id or not product_text:
            await cb.message.answer(
                "⚠️ Данных не хватает. Начни заново из меню.",
                reply_markup=kb_back_to_menu(),
                parse_mode=PARSE_MODE,
            )
            await state.clear()
            return

        credits = await safe_get_balance(cb.from_user.id)
        if credits < video_count:
            await cb.message.answer(
                f"❌ Недостаточно кредитов.\n\nНужно: <b>{video_count}</b>\nУ вас: <b>{credits}</b>",
                reply_markup=kb_no_credits(),
                parse_mode=PARSE_MODE,
            )
            await state.clear()
            return

        # Отправляем сразу уведомление о начале генерации
        await cb.message.answer(
            f"✅ <b>Принял!</b>\n\n"
            f"🎬 Генерация <b>{video_count} {'видео' if video_count == 1 else 'видео'}</b> запущена!\n\n"
            f"⏱ <b>Ожидайте</b> — это может занять от 1 до 30 минут в зависимости от загруженности Sora 2.\n\n"
            f"Я пришлю результаты сюда по мере готовности.",
            reply_markup=kb_back_to_menu(),
            parse_mode=PARSE_MODE,
        )

        # Запускаем генерацию для каждого видео
        for i in range(video_count):
            # Уникальный idempotency_key для каждого видео
            idempotency_key = f"{cb.id}_{i}"
            
            job_id, _new_credits = await start_generation(
                bot=cb.bot,
                tg_user_id=cb.from_user.id,
                idempotency_key=idempotency_key,
                photo_file_id=photo_file_id,
                kind=kind,
                product_info={"text": product_text, "user_prompt": user_prompt},
                extra_wishes=extra_wishes,
                template_id=template_id,
            )

        await state.clear()
    except Exception as e:
        logging.error(f"Error in confirm_generation: {e}", exc_info=True)
        await cb.message.answer(
            "⚠️ Ошибка, попробуй ещё раз",
            reply_markup=kb_back_to_menu(),
            parse_mode=PARSE_MODE,
        )

# Handler для "Сделать ещё с этим товаром"
@router.callback_query(F.data.startswith("retry:"))
async def retry_same_product(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    
    # Получаем job_id из предыдущей генерации
    job_id = cb.data.split(":", 1)[1]
    
    # Загружаем данные job из БД
    from app.db_adapter import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            "SELECT input_photo_path, product_info FROM jobs WHERE id::text = $1",
            job_id
        )
    
    if not job:
        await cb.message.answer(
            "⚠️ Не удалось загрузить данные предыдущей генерации.",
            reply_markup=kb_back_to_menu(),
            parse_mode=PARSE_MODE,
        )
        return
    
    # Восстанавливаем данные в state
    product_info = ensure_dict(job["product_info"])
    
    await state.update_data(
        photo_file_id=job["input_photo_path"],
        product_text=product_info.get("text", ""),
    )
    
    # Переходим к выбору шаблона
    await cb.message.answer(
        "🎬 <b>Отлично! Делаем ещё видео с этим товаром.</b>\n\n"
        "Выбери формат:",
        reply_markup=kb_template_type(),
        parse_mode=PARSE_MODE,
    )
    await state.set_state(GenFlow.waiting_template_type)

