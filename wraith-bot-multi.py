import os
import asyncio
import discord
from discord.ext import commands
from TikTokLive import TikTokLiveClient
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Bot token
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("Discord bot token (TOKEN) is missing in .env file.")

# Cache for parsed configurations
users = {}
servers = {}
test_server = {}

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Intents for the bot
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True  # Needed for message handling
bot = commands.Bot(command_prefix="!", intents=intents)

# Cache for live status to reduce API calls
live_status_cache = {}


# Configuration Parsing
def parse_env():
    """Parse the .env file with the revised structure."""
    global users, servers, test_server

    # Parse unified user configurations
    for key, value in os.environ.items():
        if key.startswith("USER_"):
            user_key = key.split("USER_", 1)[1]
            users[user_key] = parse_config_string(value)
            logger.info(f"Parsed user config: {user_key} -> {users[user_key]}")

    # Parse server configurations
    for key, value in os.environ.items():
        if key.startswith("SERVER_"):
            server_key = key.split("SERVER_", 1)[1]
            servers[server_key] = parse_config_string(value)
            logger.info(f"Parsed server config: {server_key} -> {servers[server_key]}")

    # Parse test server configuration
    test_server_config = os.getenv("TEST_SERVER")
    if test_server_config:
        test_server = parse_config_string(test_server_config)
        logger.info(f"Parsed test server config: {test_server}")


def parse_config_string(config_string):
    """
    Parse a configuration string into a dictionary.

    Example:
    "type: special, server: 1234567890, message: Alert!" ->
    {'type': 'special', 'server': '1234567890', 'message': 'Alert!'}
    """
    return {
        part.split(":")[0].strip(): part.split(":")[1].strip()
        for part in config_string.split(",")
        if ":" in part
    }


# Validate Configurations
def validate_parsed_config():
    """Validate parsed configurations."""
    # Validate users
    for user, config in users.items():
        if "type" not in config or config["type"] not in ["special", "vip"]:
            raise ValueError(f"Invalid type for user {user}: {config.get('type')}")
        if "server" not in config or not config["server"].isnumeric():
            raise ValueError(f"Invalid or missing server ID for user {user}")
        if "message" not in config or not config["message"]:
            raise ValueError(f"Missing message for user {user}")

    # Validate servers
    for server, config in servers.items():
        if "announce_channel" not in config or not config["announce_channel"].isnumeric():
            raise ValueError(f"Invalid or missing announce channel ID for server {server}")
        if "owner_stream_channel" not in config or not config["owner_stream_channel"].isnumeric():
            raise ValueError(f"Invalid or missing owner stream channel ID for server {server}")
        if "role" not in config or not config["role"]:
            raise ValueError(f"Missing role for server {server}")
        if "owner_tiktok" not in config or not config["owner_tiktok"]:
            raise ValueError(f"Missing owner TikTok username for server {server}")

    # Validate test server
    if test_server:
        if "guild" not in test_server or not test_server["guild"].isnumeric():
            raise ValueError("Invalid or missing guild ID for test server")
        if "announce_channel" not in test_server or not test_server["announce_channel"].isnumeric():
            raise ValueError("Invalid or missing announce channel ID for test server")
    logger.info("Validation of configurations passed.")


# Announcement Function
async def send_announcement(username, tiktok_url):
    """Send an announcement for a TikTok user."""
    user_config = users.get(username)
    if not user_config:
        logger.warning(f"No configuration found for user: {username}")
        return

    server_id = user_config.get("server")
    message = user_config.get("message").replace("{url}", tiktok_url)

    # Example of fetching a server config to send the announcement
    server_config = servers.get(server_id)
    if server_config:
        announce_channel_id = server_config.get("announce_channel")
        guild = bot.get_guild(int(server_id))
        announce_channel = guild.get_channel(int(announce_channel_id)) if guild else None

        if announce_channel:
            try:
                await announce_channel.send(message)
                logger.info(f"Announcement sent for {username} to {announce_channel}")
            except discord.Forbidden:
                logger.error(f"Permission denied for channel {announce_channel_id}")
            except discord.HTTPException as e:
                logger.error(f"HTTPException while sending message: {e}")
        else:
            logger.warning(f"Channel not found: {announce_channel_id}")
    else:
        logger.warning(f"Server configuration missing for server: {server_id}")


# TikTok Live Status Check
async def check_tiktok_live(username):
    """Check TikTok live status and send announcements."""
    if username in live_status_cache and live_status_cache[username]:
        logger.info(f"Cached live status for {username} valid. Skipping check.")
        return

    client = TikTokLiveClient(unique_id=username)
    try:
        logger.info(f"Checking live status for {username}...")
        live_status = await asyncio.wait_for(client.is_live(), timeout=5)
        tiktok_url = f"https://www.tiktok.com/@{username}/live"
        if live_status:
            await send_announcement(username, tiktok_url)
            live_status_cache[username] = True
        else:
            live_status_cache[username] = False
    except asyncio.TimeoutError:
        logger.warning(f"Timeout checking live status for {username}.")
    except Exception as e:
        logger.error(f"Error checking live status for {username}: {e}")


# Bot Events
@bot.event
async def on_ready():
    logger.info(f"Bot logged in as {bot.user}")
    await bot.change_presence(activity=discord.Game(name="Doing Wraith Bot Stuff"))
    await asyncio.gather(*(check_tiktok_live(username) for username in users.keys()))
    logger.info("Initial live status check complete.")


# Main Functionality
if __name__ == "__main__":
    parse_env()
    validate_parsed_config()
    bot.run(TOKEN)
