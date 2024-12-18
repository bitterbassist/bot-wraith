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

# Updated intents configuration with minimal needed permissions
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True  # Allows reading message content
intents.messages = True  # Enables message handling
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
    test_guild = bot.get_guild(int(test_server_id)) if test_server_id else None
    if test_guild:
        debug_channel = test_guild.get_channel(int(debug_channel_id)) if debug_channel_id else None
        if debug_channel:
            await debug_channel.send(f"`DEBUG LOG:` {log_message}")

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")

    # Print intents to ensure they are correctly set
    print("Intents Configuration:")
    print(f"Guilds Intent: {bot.intents.guilds}")
    print(f"Members Intent: {bot.intents.members}")
    print(f"Message Content Intent: {bot.intents.message_content}")

    # Set the custom status for the bot
    await bot.change_presence(
        activity=discord.Game(name="Doing Wraith Bot Stuff")
    )

    print("Starting initial live status check...")
    for username in TIKTOK_USERS:
        if not username.strip():
            continue
        client = TikTokLiveClient(unique_id=username)
        try:
            print(f"Checking live status for {username}...")
            live_status = await asyncio.wait_for(client.is_live(), timeout=5)
            print(f"Live status for {username}: {live_status}")
            if live_status:
                tiktok_url = f"https://www.tiktok.com/@{username}/live"
                message_sent = False

                # Send announcements to configured servers
                for server_config in SERVER_CONFIGS.get("production", []):
                    announce_channel_id = server_config.get("announce_channel_id")
                    guild_id = server_config.get("guild_id")
                    if guild_id and announce_channel_id:
                        guild = bot.get_guild(int(guild_id))
                        announce_channel = guild.get_channel(int(announce_channel_id)) if guild else None
                        if announce_channel:
                            message = f"{username} is now live! 🎥 \n🔗 Watch here: {tiktok_url}"
                            await announce_channel.send(message)
                            print(f"Announcement sent for {username} to {announce_channel}.")
                            message_sent = True
                        else:
                            print(f"Could not find guild/channel for {guild_id}/{announce_channel_id}.")
                
                if not message_sent:
                    print(f"No announcement sent for {username}. Configuration missing.")
        except asyncio.TimeoutError:
            print(f"Timeout checking live status for {username}.")
        except Exception as e:
            error_message = f"Error checking live status for {username}: {e}"
            print(error_message)
            await send_debug_logs_to_channel(error_message)

    print("Initial live status check complete.")

if __name__ == "__main__":
    bot.run(TOKEN)
