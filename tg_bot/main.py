import logging
from telegram.ext import (
    ApplicationBuilder,
    AIORateLimiter,
    CommandHandler,
    MessageHandler,
    filters,
)
from django.conf import settings
from tg_bot.handlers import (
    post_init,
    reset_persona_handle,
    start_handle,
    message_handle,
    error_handle,
)

logger = logging.getLogger(__name__)


def run_bot() -> None:
    application = (
        ApplicationBuilder()
        .token(settings.AI_TELEGRAM_BOT_TOKEN)
        .concurrent_updates(True)
        .rate_limiter(AIORateLimiter(max_retries=5))
        .http_version("1.1")
        .get_updates_http_version("1.1")
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start_handle))
    application.add_handler(CommandHandler("reset_persona", reset_persona_handle))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, message_handle)
    )
    application.add_error_handler(error_handle)

    logger.info("Starting application polling now")
    application.run_polling()
