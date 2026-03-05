import asyncio
import logging
import os
import telegram
from aiohttp import web
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.error import NetworkError, TimedOut, RetryAfter, TelegramError
from PyToday import database
from PyToday.handlers import start_command, handle_callback, handle_message, broadcast_command, admin_command
from PyToday import config

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

application = None


async def error_handler(update, context):
    try:
        raise context.error
    except NetworkError as e:
        logger.warning(f"Network error occurred: {e}. Retrying...")
        await asyncio.sleep(config.RETRY_DELAY)
    except TimedOut as e:
        logger.warning(f"Request timed out: {e}. Retrying...")
        await asyncio.sleep(config.RETRY_DELAY)
    except RetryAfter as e:
        logger.warning(f"Rate limited. Sleeping for {e.retry_after} seconds")
        await asyncio.sleep(e.retry_after)
    except TelegramError as e:
        if "Query is too old" in str(e):
            logger.warning("Callback query expired, ignoring")
        elif "Message is not modified" in str(e):
            pass
        elif "Chat not found" in str(e):
            logger.warning(f"Chat not found: {e}")
        else:
            logger.error(f"Telegram error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)


async def post_init(app):
    await database.init_db()
    logger.info("✅ Database initialized successfully")


async def health_check(request):
    return web.Response(text="Bot is running!", status=200)


async def telegram_webhook(request):
    data = await request.json()
    update = telegram.Update.de_json(data, application.bot)
    await application.process_update(update)
    return web.Response(status=200)


async def run_bot():
    global application

    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        return
    if not config.MONGODB_URI:
        logger.error("MONGODB_URI not set!")
        return

    webhook_url = os.getenv("WEBHOOK_URL")
    port = int(os.getenv("PORT", 8080))

    aio_app = web.Application()
    aio_app.router.add_get("/", health_check)
    aio_app.router.add_get("/health", health_check)
    aio_app.router.add_post("/telegram", telegram_webhook)

    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Web server started on port {port}")

    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    print("╔══════════════════════════════════════╗")
    print("║  🤖 ᴘʏᴛᴏᴅᴀʏ ᴀᴅ ʙᴏᴛ sᴛᴀʀᴛᴇᴅ          ║")
    print("║  📢 Join t.me/PythonTodayz           ║")
    print("╚══════════════════════════════════════╝")

    async with application:
        await application.bot.set_webhook(
            url=f"{webhook_url}/telegram",
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
        )
        await application.start()
        logger.info(f"✅ Webhook set to {webhook_url}/telegram")
        await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        
