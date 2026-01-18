from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ========== START ==========
def kb_continue():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Продолжить", callback_data="continue")]
    ])


# ========== MAIN MENU ==========
def kb_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Создать НЕЙРОВИДЕО", callback_data="make_reels")],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="cabinet")],
        [InlineKeyboardButton(text="🆘 Служба поддержки", callback_data="support")],
    ])


# ========== TEMPLATE ==========
def kb_templates():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ UGC блогер", callback_data="tpl:ugc")],
        [InlineKeyboardButton(text="🎥 Рекламное видео (b-roll)", callback_data="tpl:ad")],
        [InlineKeyboardButton(text="🧑‍💻 Сам себе продюсер", callback_data="tpl:self")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_menu")],
    ])


# ========== VIDEO COUNT ==========
def kb_video_count():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1️⃣ 1 видео (1 кредит)", callback_data="count:1")],
        [InlineKeyboardButton(text="3️⃣ 3 видео (3 кредита)", callback_data="count:3")],
        [InlineKeyboardButton(text="5️⃣ 5 видео (5 кредитов)", callback_data="count:5")],
        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])


# ========== CONFIRM ==========
def kb_confirm(count: int = 1):
    cost = count
    text = f"🚀 Запустить ({cost} {'кредит' if cost == 1 else 'кредита' if cost < 5 else 'кредитов'})"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data="confirm_generation")],
        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")],
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


def kb_no_credits():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="topup")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_menu")],
    ])


# после “генерация запущена”
def kb_started():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Ещё одно видео", callback_data="make_reels")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_menu")],
    ])
