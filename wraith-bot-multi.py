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
            "role_id": os.getenv(f"PRODUCTION_SERVER_CONFIG_{server_id}_ROLE_ID"),
            "owner_stream_channel_id": os.getenv(f"PRODUCTION_SERVER_CONFIG_{server_id}_OWNER_STREAM_CHANNEL_ID"),
            "owner_tiktok_username": os.getenv(f"PRODUCTION_SERVER_CONFIG_{server_id}_OWNER_TIKTOK_USERNAME"),
        }
        for server_id in PRODUCTION_SERVER_IDS if server_id
    ],
    "test": {
        "guild_id": os.getenv("TEST_SERVER_GUILD_ID"),
        "announce_channel_id": os.getenv("TEST_SERVER_ANNOUNCE_CHANNEL_ID"),
        "role_id": os.getenv("TEST_SERVER_ROLE_ID"),
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

# Helper: Find announcement channel for a guild
def get_announce_channel(guild_id):
    for server_config in SERVER_CONFIGS.get("production", []):
        if str(guild_id) == server_config.get("guild_id"):
            announce_channel_id = server_config.get("announce_channel_id")
            return int(announce_channel_id) if announce_channel_id else None
    return None

# Helper: Find role by ID
def get_role_by_id(guild, role_id):
    return discord.utils.get(guild.roles, id=int(role_id))

# Helper: Log and send debug messages
async def log_debug(message, log_to_discord=True):
    print(message)
    if log_to_discord:
        await send_debug_logs_to_channel(message)

async def send_debug_logs_to_channel(log_message):
    """Sends debug logs to a specified channel in the test server."""
    test_server_id = os.getenv("TEST_SERVER_GUILD_ID")
    debug_channel_id = os.getenv("TEST_SERVER_MONITORING_STARTED_CHANNEL_ID")
    test_guild = bot.get_guild(int(test_server_id))
    if test_guild:
        debug_channel = test_guild.get_channel(int(debug_channel_id))
        if debug_channel:
            await debug_channel.send(f"`DEBUG LOG:` {log_message}")

@bot.command()
async def check_live_all(ctx):
    """Check the live status of all monitored TikTok users."""
    results = []
    for username in TIKTOK_USERS:
        if not username.strip():
            continue
        client = TikTokLiveClient(unique_id=username)
        try:
            live_status = await client.is_live()
            status_message = f"{username} is {'live' if live_status else 'not live'}"
        except Exception as e:
            status_message = f"{username}: Error checking live status - {e}"
        results.append(status_message)
    
    if results:
        await ctx.send("\n".join(results))
    else:
        await ctx.send("No TikTok users are currently being monitored.")

@bot.command()
async def bot_status(ctx):
    """Display the bot's current status."""
    await ctx.send("Wraith Bot is online and monitoring TikTok users! 🚀")

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    await bot.change_presence(activity=discord.Game(name="Monitoring TikTok users"))

    print("Starting initial live status check...")
    for username in TIKTOK_USERS:
        if not username.strip():
            continue
        client = TikTokLiveClient(unique_id=username)

        try:
            live_status = await client.is_live()
            print(f"[DEBUG] {username} live status: {live_status}")

            if live_status:
                tiktok_url = f"https://www.tiktok.com/@{username}/live"
                message_sent, role_applied = False, False

                for server_config in SERVER_CONFIGS["production"]:
                    guild = bot.get_guild(int(server_config["guild_id"]))
                    if not guild:
                        continue

                    announce_channel_id = get_announce_channel(guild.id, SERVER_CONFIGS)
                    if announce_channel_id:
                        announce_channel = guild.get_channel(announce_channel_id)
                        if announce_channel:
                            await announce_channel.send(f"{username} is live! Watch here: {tiktok_url}")
                            message_sent = True
                    else:
                        await log_debug(bot, f"[DEBUG] No announce channel found for guild {guild.id}")

                    role_id = server_config.get("role_id")
                    if role_id:
                        role = get_role_by_id(guild, role_id)
                        member = discord.utils.find(lambda m: username.lower() in m.name.lower(), guild.members)
                        if role and member:
                            try:
                                await member.add_roles(role)
                                role_applied = True
                                print(f"[DEBUG] Role '{role.name}' applied to {username} in {guild.name}.")
                            except discord.Forbidden:
                                await log_debug(bot, f"[ERROR] No permissions to assign '{role.name}'")
                        else:
                            await log_debug(bot, f"[DEBUG] Role or member not found for {username} in {guild.name}")
        except Exception as e:
            await log_debug(bot, f"[ERROR] Exception for {username}: {e}")

@bot.command()
async def check_live_all(ctx):
    results = []
    for username in TIKTOK_USERS:
        client = TikTokLiveClient(unique_id=username)
        try:
            live_status = await client.is_live()
            results.append(f"{username} is {'live' if live_status else 'not live'}")
        except Exception as e:
            results.append(f"{username}: Error - {e}")
    await ctx.send("\n".join(results) if results else "No monitored users.")

@bot.command()
async def bot_status(ctx):
    await ctx.send("Bot is online and monitoring TikTok users! 🚀")

bot.run(TOKEN)
