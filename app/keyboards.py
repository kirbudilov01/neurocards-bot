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


# ========== TEMPLATE CHOICE ==========
def kb_template():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ UGC блогер (шаблон #1)", callback_data="template_1")],
        [InlineKeyboardButton(text="📎 Примеры шаблонов", url="https://example.com/templates")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_menu")],
    ])


# ========== CONFIRM GENERATION ==========
def kb_confirm():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить (Стоимость: 1 кредит)", callback_data="confirm_generation")],
        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])


# ========== RESULT (AFTER GENERATION) ==========
def kb_result(kind: str = "reels"):
    """
    kind: reels | neurocard
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Сгенерировать ещё видео", callback_data=f"again:{kind}")],
        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])


# ========== BACK ONLY ==========
def kb_back_to_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")]
    ])


# ========== CABINET ==========
def kb_cabinet(support_url: str = "https://t.me/your_support"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="balance")],
        [InlineKeyboardButton(text="🆘 Служба поддержиа", url=support_url)],
        [InlineKeyboardButton(text="🤝 Пригласить друзей", callback_data="ref_soon")],
        [InlineKeyboardButton(text="🏠 Вернуться в меню меню", callback_data="back_to_menu")],
    ])

def kb_after_start(kind: str = "reels"):
    # kind: "reels" | "neurocard"
    again_cb = "make_reels" if kind == "reels" else "make_neurocard"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Ещё одно видео", callback_data=again_cb)],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_menu")],
    ])
