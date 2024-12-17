import asyncio
import discord
from discord.ext import commands
from TikTokLive import TikTokLiveClient
from TikTokLive.client.logger import LogLevel
from dotenv import load_dotenv
import os
import logging

# Load environment variables
load_dotenv()

# Bot token
TOKEN = os.getenv("TOKEN")

# List of TikTok usernames
TIKTOK_USERS = os.getenv("TIKTOK_USERS", "").split(',')

# Special users: Parse from the environment variables
SPECIAL_USERS = {}
VIP_USERS = {}

for key, value in os.environ.items():
    if key.startswith("SPECIAL_USERS_"):
        username = key.split("_", 2)[2]
        SPECIAL_USERS[username] = []
        for config in value.split(";"):
            details = {
                k.strip(): v.strip() for part in config.split(",") if len(part.split(": ")) == 2 for k, v in [part.split(": ")]
            }
            SPECIAL_USERS[username].append(details)
    elif key.startswith("VIP_USERS_"):
        username = key.split("_", 2)[2]
        VIP_USERS[username] = []
        for config in value.split(";"):
            details = {
                k.strip(): v.strip() for part in config.split(",") if len(part.split(": ")) == 2 for k, v in [part.split(": ")]
            }
            VIP_USERS[username].append(details)

# Dynamically load production server configurations
PRODUCTION_SERVER_IDS = [
    os.getenv("PRODUCTION_SERVER_GUILD_ID_1307019842410516573"),
    os.getenv("PRODUCTION_SERVER_GUILD_ID_768792770734981141"),
    os.getenv("PRODUCTION_SERVER_GUILD_ID_1145354259530010684"),
]

# Load all server configurations
SERVER_CONFIGS = {
    "production": [
        {
            "guild_id": server_id,
            "announce_channel_id": os.getenv(f"PRODUCTION_SERVER_CONFIG_{server_id}_ANNOUNCE_CHANNEL_ID"),
            "role_name": os.getenv(f"PRODUCTION_SERVER_CONFIG_{server_id}_ROLE_NAME"),
            "owner_stream_channel_id": os.getenv(f"PRODUCTION_SERVER_CONFIG_{server_id}_OWNER_STREAM_CHANNEL_ID"),
            "owner_tiktok_username": os.getenv(f"PRODUCTION_SERVER_CONFIG_{server_id}_OWNER_TIKTOK_USERNAME"),
        }
        for server_id in PRODUCTION_SERVER_IDS if server_id
    ],
    "test": {
        "guild_id": os.getenv("TEST_SERVER_GUILD_ID"),
        "announce_channel_id": os.getenv("TEST_SERVER_ANNOUNCE_CHANNEL_ID"),
        "role_name": os.getenv("TEST_SERVER_ROLE_NAME"),
        "owner_stream_channel_id": os.getenv("TEST_SERVER_OWNER_STREAM_CHANNEL_ID"),
        "owner_tiktok_username": os.getenv("TEST_SERVER_OWNER_TIKTOK_USERNAME"),
        "monitoring_started_channel_id": os.getenv("TEST_SERVER_MONITORING_STARTED_CHANNEL_ID"),
    },
}

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Setup logger with custom formatting
def setup_logger(logger):
    class RailwayFormatter(logging.Formatter):
        def format(self, record):
            level_tag = f"@level:{record.levelname.lower()}"
            service_tag = "@service:tiktok_monitor"
            base_msg = super().format(record)
            return f"{level_tag} {service_tag} {base_msg}"

    handler = logging.StreamHandler()
    formatter = RailwayFormatter('%(asctime)s - %(name)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Cache for live status to reduce frequent checks
live_status_cache = {}

async def send_debug_logs_to_channel(log_message):
    """Sends debug logs to a specified channel in the test server."""
    test_server_id = os.getenv("TEST_SERVER_GUILD_ID")
    debug_channel_id = os.getenv("TEST_SERVER_MONITORING_STARTED_CHANNEL_ID")
    test_guild = bot.get_guild(int(test_server_id))
    if test_guild:
        debug_channel = test_guild.get_channel(int(debug_channel_id))
        if debug_channel:
            await debug_channel.send(f"`DEBUG LOG:` {log_message}")

# Add user command
@bot.command()
async def add_user(ctx, user_type: str, username: str, details: str):
    """Add a user to the specified list: special or VIP."""
    config_list = []
    for config in details.split(";"):
        config_list.append({
            k.strip(): v.strip() for part in config.split(",") if len(part.split(":")) == 2 for k, v in [part.split(":")]
        })
    if user_type.lower() == "special":
        SPECIAL_USERS[username] = config_list
        await ctx.send(f"User {username} added to SPECIAL_USERS with details: {config_list}.")
    elif user_type.lower() == "vip":
        VIP_USERS[username] = config_list
        await ctx.send(f"User {username} added to VIP_USERS with details: {config_list}.")
    else:
        await ctx.send("Invalid user type! Use 'special' or 'VIP'.")

# Remove user command
@bot.command()
async def remove_user(ctx, user_type: str, username: str):
    """Remove a user from the specified list: special or VIP."""
    if user_type.lower() == "special":
        if username in SPECIAL_USERS:
            del SPECIAL_USERS[username]
            await ctx.send(f"User {username} removed from SPECIAL_USERS.")
        else:
            await ctx.send(f"User {username} not found in SPECIAL_USERS.")
    elif user_type.lower() == "vip":
        if username in VIP_USERS:
            del VIP_USERS[username]
            await ctx.send(f"User {username} removed from VIP_USERS.")
        else:
            await ctx.send(f"User {username} not found in VIP_USERS.")
    else:
        await ctx.send("Invalid user type! Use 'special' or 'VIP'.")

# Force announce command
@bot.command()
async def force_announce(ctx, tiktok_username: str):
    """Force an announcement for a TikTok user."""
    tiktok_url = f"https://www.tiktok.com/@{tiktok_username}/live"
    message = f"\U0001F6A8 {tiktok_username} is now live on TikTok! \n\U0001F517 Watch live here: {tiktok_url}"
    await ctx.send(message)

# Test post command
@bot.command()
async def test_post(ctx):
    """Send a test message to verify bot functionality."""
    await ctx.send("\U0001F6A8 This is a test announcement from Wraith Bot. All systems are functioning correctly! \U0001F6A8")

# Ping command
@bot.command()
async def ping(ctx):
    """Simple ping command to check if the bot is online"""
    await ctx.send("Pong!")

# Check live status for all TikTok users
@bot.command()
async def check_live_all(ctx):
    """Check the live status of all monitored TikTok users."""
    results = []
    for username in TIKTOK_USERS:
        if not username.strip():
            continue
        client = TikTokLiveClient(unique_id=username)
        try:
            live_status = await client.is_live()  # Await the coroutine properly
            status_message = f"{username} is {'live' if live_status else 'not live'}"
        except Exception as e:
            status_message = f"{username}: Error checking live status - {e}"
        results.append(status_message)
        await send_debug_logs_to_channel(status_message)  # Send debug output to test channel

    if results:
        await ctx.send("\n".join(results))
    else:
        await ctx.send("No TikTok users are currently being monitored.")

# Updated on_ready function
@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")

    # Set the custom status for the bot
    await bot.change_presence(
        activity=discord.Game(name="Doing Wraith Bot Stuff")
    )

    print("Starting initial live status check...")
    results = []
    for username in TIKTOK_USERS:
        if not username.strip():
            continue
        client = TikTokLiveClient(unique_id=username)
        try:
            live_status = await client.is_live()  # Await the coroutine properly
            if live_status:
                tiktok_url = f"https://www.tiktok.com/@{username}/live"
                message = f"\U0001F6A8 {username} is already live on TikTok! \n\U0001F517 Watch live here: {tiktok_url}"
                print(message)
                results.append(message)
            else:
                print(f"{username} is not live.")
        except Exception as e:
            error_message = f"Error checking live status for {username}: {e}"
            print(error_message)
            await send_debug_logs_to_channel(error_message)

    print("Initial live status check complete.")

if __name__ == "__main__":
    bot.run(TOKEN)
