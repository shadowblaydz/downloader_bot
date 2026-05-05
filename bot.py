import asyncio
import logging
import os
import json
import re
import tempfile
from dotenv import load_dotenv

import yt_dlp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiohttp import web

from downloader import download_video

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 8080))
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN provided in the environment variables.")

# User Tracking Setup
USERS_FILE = "users.json"

def load_users():
    if not os.path.exists(USERS_FILE):
        return []
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def save_user(user_id):
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        try:
            with open(USERS_FILE, "w") as f:
                json.dump(users, f)
        except Exception as e:
            logger.error(f"Could not save user {user_id}: {e}")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

URL_REGEX = r'(https?://[^\s]+)'

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    save_user(message.from_user.id)
    await message.reply(
        "👋 Hello! I am a Video Downloader Bot.\n\n"
        "Send me a link from **YouTube**, **TikTok**, or **Instagram**, "
        "and I will download the video for you!\n\n"
        "*(Note: Maximum supported video size is 50MB due to Telegram limits)*",
        parse_mode="Markdown"
    )

@dp.message(Command("admin"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_admin(message: types.Message):
    await message.reply(
        "🛠 **Admin Panel**\n\n"
        "/stats - View total users\n"
        "/broadcast <message> - Send message to all users",
        parse_mode="Markdown"
    )

@dp.message(Command("stats"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_stats(message: types.Message):
    users = load_users()
    await message.reply(f"📊 **Bot Statistics**\n\nTotal Users: {len(users)}", parse_mode="Markdown")

@dp.message(Command("broadcast"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_broadcast(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Please provide a message to broadcast. Usage:\n`/broadcast Hello everyone!`", parse_mode="Markdown")
        return
        
    broadcast_msg = parts[1]
    users = load_users()
    sent_count = 0
    
    status_msg = await message.reply(f"🚀 Broadcasting to {len(users)} users...")
    
    for user_id in users:
        try:
            await bot.send_message(user_id, broadcast_msg)
            sent_count += 1
            await asyncio.sleep(0.05) # Prevent rate limiting
        except Exception:
            pass # User might have blocked the bot
            
    await status_msg.edit_text(f"✅ Broadcast complete!\nSent to {sent_count}/{len(users)} users.")

@dp.message(F.text)
async def handle_message(message: types.Message):
    save_user(message.from_user.id)
    match = re.search(URL_REGEX, message.text)
    if not match:
        # Ignore messages without URLs or send a prompt
        if message.chat.type == "private":
            await message.reply("Please send me a valid video link.")
        return

    url = match.group(1)
    
    # Check supported domains
    supported_domains = ['youtube.com', 'youtu.be', 'tiktok.com', 'instagram.com']
    if not any(domain in url.lower() for domain in supported_domains):
        if message.chat.type == "private":
            await message.reply("❌ Unsupported link. Please send a YouTube, TikTok, or Instagram link.")
        return

    status_msg = await message.reply("⏳ Downloading your video... Please wait.")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"Downloading video from {url}")
            downloaded_file = await download_video(url, temp_dir)

            if downloaded_file and os.path.exists(downloaded_file):
                file_size = os.path.getsize(downloaded_file)
                logger.info(f"Downloaded file size: {file_size} bytes")
                
                if file_size > 50 * 1024 * 1024:
                    await status_msg.edit_text("❌ The video is larger than Telegram's 50MB limit.")
                else:
                    await status_msg.edit_text("📤 Uploading to Telegram...")
                    video = FSInputFile(downloaded_file)
                    await message.reply_video(video=video, caption="Here is your video!")
                    await status_msg.delete()
            else:
                await status_msg.edit_text("❌ Failed to download the video.")

    except yt_dlp.utils.DownloadError as e:
        logger.error(f"DownloadError for {url}: {e}")
        await status_msg.edit_text("❌ Could not download the video. The link might be private, invalid, or unsupported.")
    except Exception as e:
        logger.error(f"Error processing {url}: {e}")
        await status_msg.edit_text("❌ Something went wrong while processing your request.")

# Health check endpoint for Railway
async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_bot():
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot polling error: {e}")

async def on_startup(app):
    # Start the bot polling in the background when the web server starts
    asyncio.create_task(start_bot())

async def main():
    logger.info("Starting up application...")
    
    # Initialize aiohttp application
    app = web.Application()
    app.router.add_get('/', health_check)
    app.on_startup.append(on_startup)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Bind to 0.0.0.0 and the PORT environment variable
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    logger.info(f"Starting health check web server on port {PORT}")
    await site.start()
    
    # Keep the main coroutine running
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
