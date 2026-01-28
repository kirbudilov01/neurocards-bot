"""
Webhook handlers for payment processing
This module handles incoming payment confirmations from Yookassa
"""
import logging
from fastapi import APIRouter, Request, HTTPException
from app.services.payment import PaymentService
from app.db_adapter import execute_db_query
from aiogram import Bot
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhooks"])

BOT_TOKEN = os.getenv("BOT_TOKEN", "")


@router.post("/yookassa")
async def yookassa_webhook(request: Request):
    """
    Handle Yookassa payment webhooks
    
    Yookassa sends POST requests to this endpoint when payment status changes
    Updates user balance in DB and notifies via bot
    """
    try:
        # Get raw body for signature verification
        body = await request.body()
        data = await request.json()
        
        logger.info(f"📨 Received Yookassa webhook: {data.get('event')}")
        
        # Verify webhook signature (optional - depends on your setup)
        # signature = request.headers.get("X-Yookassa-Webhook-Id", "")
        # if not PaymentService.verify_webhook(data, signature):
        #     logger.warning("❌ Invalid webhook signature")
        #     raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Extract payment info
        payment_info = PaymentService.extract_payment_info(data)
        if not payment_info:
            logger.warning("⚠️ Could not extract payment info from webhook")
            return {"status": "ignored"}
        
        payment_id = payment_info["payment_id"]
        status = payment_info["status"]
        user_id = payment_info["user_id"]
        credits = payment_info["credits"]
        
        logger.info(f"💳 Payment {payment_id} - status: {status}, user: {user_id}, credits: {credits}")
        
        # Handle payment based on status
        if status == "succeeded":
            # Update user balance in database
            try:
                await execute_db_query(
                    "UPDATE users SET credits = credits + $1 WHERE tg_id = $2",
                    credits,
                    user_id
                )
                logger.info(f"✅ Credits added: user {user_id} +{credits}")
                
                # Notify user via bot
                if BOT_TOKEN:
                    bot = Bot(token=BOT_TOKEN)
                    try:
                        await bot.send_message(
                            user_id,
                            f"✅ <b>Платеж успешно обработан!</b>\n\n"
                            f"На ваш баланс добавлено: <b>{credits} кредит(ов)</b>\n\n"
                            f"💳 Спасибо за поддержку! 🎉",
                            parse_mode="HTML"
                        )
                    except Exception as notify_error:
                        logger.warning(f"⚠️ Failed to notify user {user_id}: {notify_error}")
                    finally:
                        await bot.session.close()
                
                return {"status": "success", "message": f"Credits added for user {user_id}"}
                
            except Exception as db_error:
                logger.error(f"❌ Database error: {db_error}", exc_info=True)
                raise HTTPException(status_code=500, detail="Database error")
        
        elif status == "canceled":
            logger.info(f"ℹ️ Payment canceled by user: {payment_id}")
            # Optionally notify user
            if BOT_TOKEN:
                bot = Bot(token=BOT_TOKEN)
                try:
                    await bot.send_message(
                        user_id,
                        f"ℹ️ Платеж отменён.\n\nЕсли это произошло по ошибке, попробуйте ещё раз.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
                finally:
                    await bot.session.close()
            
            return {"status": "canceled"}
        
        else:
            logger.info(f"ℹ️ Payment in status: {status}")
            return {"status": status}
    
    except Exception as e:
        logger.error(f"❌ Webhook processing error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
