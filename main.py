import asyncio
import logging
import os
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.error import NetworkError, TimedOut, RetryAfter, TelegramError
from PyToday import database
from PyToday.handlers import start_command, handle_callback, handle_message, broadcast_command, admin_command
from PyToday import config
from aiohttp import web

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

async def error_handler(update, context):
    try:
        raise context.error
    except NetworkError as e:
        logger.warning(f"Network error: {e}")
    except TimedOut as e:
        logger.warning(f"Timeout: {e}")
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after)
    except TelegramError as e:
        logger.error(f"Telegram error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)

async def health_check(request):
    return web.Response(text="Bot is running!", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Web server started on port {port}")

async def main():
    await database.init_db()

    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .build()
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    await application.initialize()
    await application.start()

    asyncio.create_task(start_web_server())

    await application.updater.start_polling()

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
