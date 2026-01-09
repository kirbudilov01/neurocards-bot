
import os
import sentry_sdk
from sentry_sdk.integrations.aiohttp import AioHttpIntegration

def setup_sentry():
    """
    Configures Sentry for error reporting if a DSN is provided.
    """
    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[AioHttpIntegration()],
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
        )
