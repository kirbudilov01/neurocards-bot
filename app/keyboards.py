from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ========== START ==========
def kb_continue():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Продолжить", callback_data="continue")]
    ])


# ========== MAIN MENU ==========
def kb_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Создать REELS ВИДЕО", callback_data="make_reels")],
        [InlineKeyboardButton(text="🧠 Создать НЕЙРОКАРТОЧКУ", callback_data="make_neurocard")],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="cabinet")],
        [InlineKeyboardButton(text="🆘 Служба поддержки", callback_data="support")],
    ])


# ========== TEMPLATE ==========
def kb_template():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ UGC блогер (шаблон #1)", callback_data="template_1")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_menu")],
    ])


# ========== CONFIRM ==========
def kb_confirm():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить (1 кредит)", callback_data="confirm_generation")],
        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])


# ========== AFTER GENERATION ==========
def kb_result(kind: str = "reels"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Сгенерировать ещё", callback_data=f"again:{kind}")],
        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])


def kb_after_start(kind: str = "reels"):
    again_cb = "make_reels" if kind == "reels" else "make_neurocard"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Ещё одно видео", callback_data=again_cb)],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_menu")],
    ])


# ========== BACK ==========
def kb_back_to_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")]
    ])


# ========== TOP UP ==========
def kb_topup():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5 токенов — 390 ₽", callback_data="pay:5")],
        [InlineKeyboardButton(text="10 токенов — 690 ₽", callback_data="pay:10")],
        [InlineKeyboardButton(text="30 видео — 1 790 ₽", callback_data="pay:30")],
        [InlineKeyboardButton(text="100 видео — 4 990 ₽", callback_data="pay:100")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_menu")],
    ])


# ========== CABINET ==========
def kb_cabinet(support_url: str = "https://t.me/your_support"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="topup")],
        [InlineKeyboardButton(text="🆘 Служба поддержки", url=support_url)],
        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])
