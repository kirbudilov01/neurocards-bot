from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def kb_continue():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Продолжить", callback_data="continue")]
    ])

def kb_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Создать REELS ВИДЕО", callback_data="make_reels")],
        [InlineKeyboardButton(text="🧠 Создать НЕЙРОКАРТОЧКУ", callback_data="make_neurocard")],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="cabinet")],
        [InlineKeyboardButton(text="🆘 Служба поддержки", callback_data="support")],
    ])

def kb_template():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Шаблон #1", callback_data="template_1")],
        [InlineKeyboardButton(text="📎 Примеры шаблонов", url="https://example.com/templates")],
    ])

def kb_confirm():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить (1 кредит)", callback_data="confirm_generation")],
        [InlineKeyboardButton(text="↩️ Отмена", callback_data="cancel")],
    ])

def kb_back_to_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_menu")]
    ])

def kb_cabinet(support_url: str = "https://t.me/your_support"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆘 Поддержка", url=support_url)],
        [InlineKeyboardButton(text="🤝 Реф. система (скоро)", callback_data="ref_soon")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_menu")],
    ])
