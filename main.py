
import asyncio
import logging
import time
import os
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.error import NetworkError, TimedOut, RetryAfter, TelegramError
from PyToday import database
from PyToday.handlers import start_command, handle_callback, handle_message, broadcast_command, admin_command
from PyToday import config
from aiohttp import web

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)


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


async def post_init(application):
    await database.init_db()
    logger.info("✅ Database initialized successfully")


async def health_check(request):
    return web.Response(text="Bot is running!", status=200)


async def start_web_server():
    """Start aiohttp web server on the same event loop as the bot."""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)

    port = int(os.getenv('PORT', 8080))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    logger.info(f"🌐 Web server started on port {port}")
    return runner


async def run_bot():
    """Run bot and web server together on the same event loop."""
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        return
    if not config.MONGODB_URI:
        logger.error("MONGODB_URI not set!")
        return

    # Start web server on the same loop — no threads needed
    web_runner = await start_web_server()

    print("╔══════════════════════════════════════╗")
    print("║  🤖 ᴘʏᴛᴏᴅᴀʏ ᴀᴅ ʙᴏᴛ sᴛᴀʀᴛᴇᴅ          ║")
    print("║  📢 Join t.me/PythonTodayz           ║")
    print("╚══════════════════════════════════════╝")

    while True:
        try:
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

            async with application:
                await application.start()
                await application.updater.start_polling(
                    allowed_updates=["message", "callback_query"],
                    drop_pending_updates=True,
                    poll_interval=1.0,
                    timeout=30
                )
                # Keep running until interrupted
                await asyncio.Event().wait()

        except (NetworkError, TimedOut) as e:
            logger.error(f"Network error, restarting in {config.RETRY_DELAY}s: {e}")
            await asyncio.sleep(config.RETRY_DELAY)
        except asyncio.CancelledError:
            logger.info("Bot stopped.")
            break
        except Exception as e:
            logger.error(f"Fatal error, restarting in {config.RETRY_DELAY}s: {e}", exc_info=True)
            await asyncio.sleep(config.RETRY_DELAY)
        finally:
            if web_runner:
                await web_runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
