"""
Payment service for Yookassa integration
Handles payment creation, webhooks, and credit updates
"""
import os
import logging
from typing import Optional
import uuid
import hashlib

logger = logging.getLogger(__name__)

# Yookassa credentials
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_API_KEY = os.getenv("YOOKASSA_API_KEY", "")
YOOKASSA_WEBHOOK_SECRET = os.getenv("YOOKASSA_WEBHOOK_SECRET", "")

# Price mapping: credits -> amount in rubles
PRICE_TIERS = {
    5: 390,      # 5 tokens = 390 ₽
    10: 690,     # 10 tokens = 690 ₽
    30: 1790,    # 30 videos = 1790 ₽
    100: 4990,   # 100 videos = 4990 ₽
}

# Reverse mapping for verification
PRICE_TO_CREDITS = {v: k for k, v in PRICE_TIERS.items()}


class PaymentService:
    """Service for handling Yookassa payments"""
    
    @staticmethod
    def is_configured() -> bool:
        """Check if Yookassa is properly configured"""
        return bool(YOOKASSA_SHOP_ID and YOOKASSA_API_KEY)
    
    @staticmethod
    def create_payment(user_id: int, credits: int) -> Optional[dict]:
        """
        Create a payment in Yookassa
        
        Returns:
            dict with payment_id and confirmation_url, or None if not configured
        """
        if not PaymentService.is_configured():
            logger.warning("❌ Yookassa not configured - returning test payment")
            return PaymentService._create_test_payment(user_id, credits)
        
        if credits not in PRICE_TIERS:
            logger.error(f"❌ Invalid credit amount: {credits}")
            return None
        
        try:
            import httpx
            from base64 import b64encode
            
            amount_kopeks = PRICE_TIERS[credits] * 100
            payment_id = str(uuid.uuid4())
            
            # Basic Auth for Yookassa API
            auth_str = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_API_KEY}"
            auth_b64 = b64encode(auth_str.encode()).decode()
            
            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Idempotence-Key": payment_id,
                "Content-Type": "application/json",
            }
            
            payload = {
                "amount": {
                    "value": f"{PRICE_TIERS[credits]}.00",
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"https://t.me/neurocards_bot"  # Redirect back to bot
                },
                "receipt": {
                    "customer": {
                        "full_name": f"User {user_id}",
                        "email": f"user{user_id}@bot.local"
                    },
                    "items": [{
                        "description": f"{credits} Credits for NeuroCards",
                        "quantity": "1.00",
                        "amount": {
                            "value": f"{PRICE_TIERS[credits]}.00",
                            "currency": "RUB"
                        },
                        "vat_code": 1
                    }]
                },
                "metadata": {
                    "user_id": str(user_id),
                    "credits": str(credits),
                }
            }
            
            # Make request to Yookassa API
            client = httpx.Client(timeout=30.0)
            response = client.post(
                "https://api.yookassa.ru/v3/payments",
                json=payload,
                headers=headers
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                logger.info(f"✅ Payment created: {data.get('id')}")
                return {
                    "payment_id": data.get("id"),
                    "confirmation_url": data.get("confirmation", {}).get("confirmation_url"),
                    "status": "pending"
                }
            else:
                logger.error(f"❌ Yookassa error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Payment creation failed: {e}", exc_info=True)
            return None
    
    @staticmethod
    def _create_test_payment(user_id: int, credits: int) -> dict:
        """
        Create a test payment (for development without Yookassa)
        In production, replace with actual Yookassa API call
        """
        payment_id = f"test_{uuid.uuid4().hex[:8]}"
        logger.info(f"🧪 Test payment created: {payment_id} for user {user_id}, credits {credits}")
        return {
            "payment_id": payment_id,
            "confirmation_url": f"https://pay.test/{payment_id}",
            "status": "pending",
            "is_test": True
        }
    
    @staticmethod
    def verify_webhook(data: dict, signature: str) -> bool:
        """
        Verify Yookassa webhook signature
        
        Args:
            data: webhook payload
            signature: X-Yookassa-Webhook-Id header value
        
        Returns:
            True if signature is valid
        """
        if not YOOKASSA_WEBHOOK_SECRET:
            logger.warning("⚠️ YOOKASSA_WEBHOOK_SECRET not set - skipping signature verification")
            return True
        
        try:
            import json
            
            # Reconstruct the message that was signed
            webhook_content = json.dumps(data, ensure_ascii=False, sort_keys=True)
            
            # Compute HMAC-SHA256
            import hmac
            computed_signature = hmac.new(
                YOOKASSA_WEBHOOK_SECRET.encode(),
                webhook_content.encode(),
                hashlib.sha256
            ).hexdigest()
            
            is_valid = computed_signature == signature
            if not is_valid:
                logger.warning(f"❌ Webhook signature mismatch")
            return is_valid
        except Exception as e:
            logger.error(f"❌ Signature verification failed: {e}")
            return False
    
    @staticmethod
    def extract_payment_info(webhook_data: dict) -> Optional[dict]:
        """
        Extract payment info from Yookassa webhook
        
        Returns:
            dict with payment_id, status, user_id, credits or None
        """
        try:
            event_type = webhook_data.get("event")
            payment_data = webhook_data.get("object", {})
            
            if event_type not in ["payment.succeeded", "payment.canceled"]:
                logger.info(f"ℹ️ Ignoring event: {event_type}")
                return None
            
            payment_id = payment_data.get("id")
            status = payment_data.get("status")
            
            # Get metadata
            metadata = payment_data.get("metadata", {})
            user_id = metadata.get("user_id")
            credits = metadata.get("credits")
            
            if not all([payment_id, user_id, credits]):
                logger.error("❌ Missing required fields in webhook")
                return None
            
            return {
                "payment_id": payment_id,
                "status": status,
                "user_id": int(user_id),
                "credits": int(credits),
            }
        except Exception as e:
            logger.error(f"❌ Failed to extract payment info: {e}")
            return None
