from io import BytesIO
from aiogram import Bot

async def download_photo_bytes(bot: Bot, file_id: str) -> bytes:
    file = await bot.get_file(file_id)
    buf = BytesIO()
    await bot.download_file(file.file_path, destination=buf)
    return buf.getvalue()
