import asyncio
import discord
from discord.ext import commands
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent
from TikTokLive.client.errors import UserOfflineError
from dotenv import load_dotenv
import os
import logging
import websockets.exceptions

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

# Map TikTok usernames to Discord user IDs
USERNAME_TO_DISCORD_ID = {
    pair.split(":")[0]: int(pair.split(":")[1])
    for pair in os.getenv("USERNAME_TO_DISCORD_ID", "").split(",")
    if ":" in pair
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

def create_tiktok_client(username):
    client = TikTokLiveClient(unique_id=username)

    @client.on(ConnectEvent)
    async def on_connect(event):
        print(f"[INFO] {username} started a live stream.")

        # Assign role and send announcement in Discord
        guild = bot.get_guild(int(os.getenv("PRODUCTION_SERVER_IDS")))
        role_name = os.getenv("ROLE_NAME", "Live Now")
        role = discord.utils.get(guild.roles, name=role_name)
        discord_id = USERNAME_TO_DISCORD_ID.get(username)
        if discord_id:
            member = guild.get_member(discord_id)
            if member and role:
                await member.add_roles(role)
                channel = bot.get_channel(int(os.getenv("ANNOUNCE_CHANNEL_ID")))
                await channel.send(f"{member.mention} is now live on TikTok! Watch here: https://www.tiktok.com/@{username}/live")

    @client.on(DisconnectEvent)
    async def on_disconnect(event):
        print(f"[INFO] {username} ended the live stream.")

        # Remove role in Discord
        guild = bot.get_guild(int(os.getenv("PRODUCTION_SERVER_IDS")))
        role_name = os.getenv("ROLE_NAME", "Live Now")
        role = discord.utils.get(guild.roles, name=role_name)
        discord_id = USERNAME_TO_DISCORD_ID.get(username)
        if discord_id:
            member = guild.get_member(discord_id)
            if member and role:
                await member.remove_roles(role)
                channel = bot.get_channel(int(os.getenv("ANNOUNCE_CHANNEL_ID")))
                await channel.send(f"{member.mention} has ended their TikTok live stream.")

    return client

async def start_tiktok_clients():
    async def handle_client(username):
        """Handle connection and retries for a single TikTok user."""
        client = create_tiktok_client(username)
        while True:
            try:
                print(f"[INFO] Attempting to connect to {username}'s TikTok live...")
                await client.connect()
            except UserOfflineError:
                print(f"[DEBUG] {username} is offline. Retrying in 60 seconds...")
                await asyncio.sleep(60)  # Retry after delay
            except websockets.exceptions.ConnectionClosedError as e:
                print(f"[ERROR] WebSocket connection closed for {username}: {e}. Retrying in 30 seconds...")
                await asyncio.sleep(30)  # Retry WebSocket connection
            except Exception as e:
                print(f"[ERROR] An unexpected error occurred for {username}: {e}")
                break  # Stop retrying on unexpected errors

    # Start a coroutine for each TikTok username
    for username in TIKTOK_USERS:
        if username.strip():
            bot.loop.create_task(handle_client(username))
@bot.command(name="announce_live")
async def announce_live(ctx, username: str):
    """
    Manually announce that a TikTok user is live.
    
    Usage:
    !announce_live <TikTokUsername>
    """
    try:
        username = username.strip()
        if username not in TIKTOK_USERS:
            await ctx.send(f"Error: {username} is not in the monitored TikTok users list.")
            return

        # Determine the guild and announcement channel
        guild_id = next((server for server, details in SPECIAL_USERS.get(username, []) if "server" in details), None)
        if not guild_id or guild_id not in PROD_SERVERS:
            await ctx.send(f"Error: No valid server configuration found for {username}.")
            return

        guild_config = PROD_SERVERS[guild_id]
        guild = bot.get_guild(int(guild_id))
        if not guild:
            await ctx.send(f"Error: Could not find guild with ID {guild_id}.")
            return

        channel_id = guild_config["announce_channel"]
        channel = guild.get_channel(int(channel_id))
        if not channel:
            await ctx.send(f"Error: Announcement channel not found for {username}.")
            return

        # Get custom message if available
        message = VIP_USERS.get(username, {}).get("message", f"{username} is now live on TikTok! Watch here: https://www.tiktok.com/@{username}/live")
        await channel.send(message)
        await ctx.send(f"Announcement sent: {message}")
        logger.info(f"Manual announcement sent for {username} by {ctx.author}.")
    except Exception as e:
        logger.exception(f"Error while manually announcing {username}: {e}")
        await ctx.send(f"An error occurred while processing the announcement for {username}.")

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")

    # Start TikTok clients asynchronously
    bot.loop.create_task(start_tiktok_clients())

if __name__ == "__main__":
    bot.run(TOKEN)
