
import pytest
from unittest.mock import AsyncMock, patch
from app.services.generation import start_generation

@pytest.mark.asyncio
async def test_start_generation_sends_message():
    # Mock bot
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()

    # Mock dependencies
    with patch('app.services.generation.download_photo_bytes', return_value=b'test_photo_bytes'), \
         patch('app.services.generation.upload_input_photo', return_value=None), \
         patch('app.services.generation.create_job_and_consume_credit', return_value={'job_id': 'test_job_id', 'new_credits': 9}), \
         patch('app.services.generation.get_queue_position', return_value=1), \
         patch('app.services.generation.get_job_by_idempotency_key', return_value=None):

            # Call the function
            await start_generation(
                bot=mock_bot,
                tg_user_id=123,
                idempotency_key='test_idempotency_key',
                photo_file_id='test_photo_id',
                kind='test_kind',
                product_info={},
                extra_wishes=None,
                template_id='test_template_id'
            )

    # Assert that the message was sent
    mock_bot.send_message.assert_called_once()
