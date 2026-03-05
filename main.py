import asyncio
import logging
import signal
import sys
import time
import os
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.error import NetworkError, TimedOut, RetryAfter, TelegramError
from PyToday import database
from PyToday.handlers import start_command, handle_callback, handle_message, broadcast_command, admin_command
from PyToday import config

# Web server for 24/7 running
from aiohttp import web
import threading

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

# Web server handler for health checks
async def health_check(request):
    return web.Response(text="Bot is running!", status=200)

async def start_web_server():
    """Start a web server for health checks"""
    try:
        app = web.Application()
        app.router.add_get('/', health_check)
        app.router.add_get('/health', health_check)
        
        # Get port from environment variable or default to 8080
        port = int(os.getenv('PORT', 8080))
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        
        logger.info(f"🌐 Web server started on port {port}")
        return runner
    except Exception as e:
        logger.error(f"Failed to start web server: {e}")
        return None

def main():
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN not set in environment variables!")
        print("ERROR: Please set BOT_TOKEN environment variable")
        print("Get your bot token from @BotFather on Telegram")
        return
    
    if not config.MONGODB_URI:
        logger.error("MONGODB_URI not set in environment variables!")
        print("ERROR: Please set MONGODB_URI environment variable")
        return
    
    # Start web server in a separate thread
    async def run_web():
        web_runner = await start_web_server()
        while True:
            await asyncio.sleep(60)
    
    def start_web_thread():
        asyncio.run(run_web())
    
    web_thread = threading.Thread(target=start_web_thread, daemon=True)
    web_thread.start()
    
    logger.info("🤖 Bot started successfully!")
    print("╔══════════════════════════════════════╗")
    print("║  🤖 ᴘʏᴛᴏᴅᴀʏ ᴀᴅ ʙᴏᴛ sᴛᴀʀᴛᴇᴅ          ║")
    print("║  📢 Join t.me/PythonTodayz           ║")
    print("╚══════════════════════════════════════╝")
    
    while True:
        try:
            # Create application
            application = (
                Application.builder()
                .token(config.BOT_TOKEN)
                .post_init(post_init)
                .build()
            )
            
            # Command handlers
            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(CommandHandler("broadcast", broadcast_command))
            application.add_handler(CommandHandler("admin", admin_command))
            
            # Callback and message handlers
            application.add_handler(CallbackQueryHandler(handle_callback))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            
            application.add_error_handler(error_handler)
            
            # Run the bot
            application.run_polling(
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True,
                poll_interval=1.0,
                timeout=30
            )
            
        except NetworkError as e:
            logger.error(f"Network error, restarting in {config.RETRY_DELAY}s: {e}")
            time.sleep(config.RETRY_DELAY)
        except TimedOut as e:
            logger.error(f"Timeout error, restarting in {config.RETRY_DELAY}s: {e}")
            time.sleep(config.RETRY_DELAY)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"Fatal error, restarting in {config.RETRY_DELAY}s: {e}", exc_info=True)
            time.sleep(config.RETRY_DELAY)

if __name__ == "__main__":
    main()
