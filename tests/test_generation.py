
import pytest
from unittest.mock import AsyncMock, patch
from app.services.generation import start_generation

@pytest.mark.asyncio
@patch('app.db.create_client')
async def test_start_generation_sends_message(mock_create_client):
    # Mock bot
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()

    # Mock dependencies
    with patch('app.services.generation.download_photo_bytes', new_callable=AsyncMock) as mock_download, \
         patch('app.services.generation.upload_input_photo', new_callable=AsyncMock) as mock_upload, \
         patch('app.services.generation.create_job_and_consume_credit', new_callable=AsyncMock) as mock_create_job, \
         patch('app.services.generation.get_queue_position', new_callable=AsyncMock) as mock_get_queue, \
         patch('app.services.generation.get_job_by_idempotency_key', new_callable=AsyncMock) as mock_get_job:

        mock_create_job.return_value = {'job_id': 'test_job_id', 'new_credits': 9}
        mock_get_job.return_value = None

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
