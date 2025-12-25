from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def kb_cabinet(support_url: str = "https://t.me/your_support", ref_code: str | None = None):
    # ref_code можно пока не использовать — оставим на будущее
    buttons = [
        [InlineKeyboardButton(text="🆘 Поддержка", url=support_url)],
        [InlineKeyboardButton(text="🤝 Реф. система (скоро)", callback_data="ref_soon")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
