
import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.generation import start_generation

@pytest.mark.asyncio
@patch('uuid.uuid4')
@patch('app.services.generation.download_photo_bytes', new_callable=AsyncMock)
@patch('app.services.generation.upload_input_photo')
@patch('app.services.generation.get_job_by_idempotency_key')
@patch('app.services.generation.create_job_and_consume_credit')
@patch('app.services.generation.get_user_balance')
async def test_start_generation_idempotency_efficiency(
    mock_get_user_balance,
    mock_create_job,
    mock_get_job,
    mock_upload_photo,
    mock_download_photo,
    mock_uuid4
):
    # Mock bot
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()
    mock_uuid4.return_value.hex = 'test_uuid'

    # --- First call (job doesn't exist) ---
    mock_get_job.return_value = None
    mock_create_job.return_value = {'job_id': 'test_job_id', 'new_credits': 9}

    await start_generation(
        bot=mock_bot,
        tg_user_id=123,
        idempotency_key='test_key',
        photo_file_id='test_photo_id',
        kind='test_kind',
        product_info={},
        extra_wishes=None,
        template_id='test_template_id'
    )

    # Assert that I/O and DB write operations were performed
    mock_download_photo.assert_called_once()
    mock_upload_photo.assert_called_once()
    mock_create_job.assert_called_once()

    # --- Second call (job exists) ---
    mock_get_job.return_value = {'id': 'test_job_id'}

    await start_generation(
        bot=mock_bot,
        tg_user_id=123,
        idempotency_key='test_key',
        photo_file_id='test_photo_id',
        kind='test_kind',
        product_info={},
        extra_wishes=None,
        template_id='test_template_id'
    )

    # Assert that I/O and DB write operations were NOT performed again
    mock_download_photo.assert_called_once()  # Still 1
    mock_upload_photo.assert_called_once()  # Still 1
    mock_create_job.assert_called_once()  # Still 1
    mock_get_user_balance.assert_called_once_with(123)
