from aiogram.fsm.state import StatesGroup, State

class GenFlow(StatesGroup):
    waiting_photo = State()
    waiting_product_info = State()
    waiting_template = State()
    waiting_wishes = State()
    waiting_user_prompt = State()
    waiting_video_count = State()
    waiting_confirm = State()
    
    # Phase 1.5: Для циклического флоу
    # Сохраняем контекст (фото, описание товара) между генерациями
    # При "Сделать еще с этим товаром" возвращаемся к waiting_template

