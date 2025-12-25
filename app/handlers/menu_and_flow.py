from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.keyboards import kb_menu, kb_cabinet
from app import texts
from app.db import get_or_create_user, supabase

router = Router()

MENU_TEXT = getattr(texts, "MENU", "Выберите действие 👇")


def _get_balance(tg_user_id: int) -> int:
    # users.tg_user_id -> balance
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


@router.callback_query(F.data == "continue")
async def on_continue(cb: CallbackQuery):
    await cb.answer()
    get_or_create_user(cb.from_user.id, cb.from_user.username)
    await cb.message.answer(MENU_TEXT, reply_markup=kb_menu())


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(MENU_TEXT, reply_markup=kb_menu())


@router.callback_query(F.data.startswith("again:"))
async def again(cb: CallbackQuery):
    # Сейчас делаем просто и надёжно: возвращаем в меню.
    # (На следующем шаге сделаем авто-переход в нужный флоу сразу.)
    await cb.answer("Ок, давай ещё одну")
    await cb.message.answer(MENU_TEXT, reply_markup=kb_menu())


@router.callback_query(F.data == "cabinet")
async def cabinet(cb: CallbackQuery):
    await cb.answer()
    get_or_create_user(cb.from_user.id, cb.from_user.username)
    bal = _get_balance(cb.from_user.id)
    await cb.message.answer(
        f"👤 Личный кабинет\n\n💳 Баланс: {bal} кредит(ов)",
        reply_markup=kb_cabinet(),
    )


@router.callback_query(F.data == "balance")
async def balance(cb: CallbackQuery):
    await cb.answer()
    bal = _get_balance(cb.from_user.id)
    await cb.message.answer(f"💳 Ваш баланс: {bal} кредит(ов)", reply_markup=kb_cabinet())


@router.callback_query(F.data == "support")
async def support(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer("🆘 Поддержка: https://t.me/your_support", reply_markup=kb_menu())


# ВАЖНО:
# make_reels / make_neurocard / template_1 / confirm_generation
# у тебя уже есть и работает — мы их тут не переписываем.
# Если у тебя их в этом файле не было — они в другом файле/ветке логики.
