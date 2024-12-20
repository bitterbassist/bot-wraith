import asyncio
import discord
from discord.ext import commands
from TikTokLive import TikTokLiveClient
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
async def add_user(ctx, user_type: str, username: str, *, details: str):
    """Adds a user to the specified list (special or vip)."""
    user_type = user_type.lower()
    if user_type not in ["special", "vip"]:
        await ctx.send("Invalid user type. Use 'special' or 'vip'.")
        return

    if user_type == "special":
        if username not in SPECIAL_USERS:
            SPECIAL_USERS[username] = []
        SPECIAL_USERS[username].append({k.strip(): v.strip() for part in details.split(",") if len(part.split(":")) == 2 for k, v in [part.split(":")]})
        await ctx.send(f"User '{username}' added to SPECIAL_USERS with details: {details}")
    elif user_type == "vip":
        if username not in VIP_USERS:
            VIP_USERS[username] = []
        VIP_USERS[username].append({k.strip(): v.strip() for part in details.split(",") if len(part.split(":")) == 2 for k, v in [part.split(":")]})
        await ctx.send(f"User '{username}' added to VIP_USERS with details: {details}")

@bot.command()
async def remove_user(ctx, user_type: str, username: str):
    """Removes a user from the specified list (special or vip)."""
    user_type = user_type.lower()
    if user_type not in ["special", "vip"]:
        await ctx.send("Invalid user type. Use 'special' or 'vip'.")
        return

    if user_type == "special":
        if username in SPECIAL_USERS:
            del SPECIAL_USERS[username]
            await ctx.send(f"User '{username}' removed from SPECIAL_USERS.")
        else:
            await ctx.send(f"User '{username}' not found in SPECIAL_USERS.")
    elif user_type == "vip":
        if username in VIP_USERS:
            del VIP_USERS[username]
            await ctx.send(f"User '{username}' removed from VIP_USERS.")
        else:
            await ctx.send(f"User '{username}' not found in VIP_USERS.")

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
            # Check live status
            live_status = await client.is_live()
            print(f"[DEBUG] {username} live status: {live_status}")

            if live_status:
                tiktok_url = f"https://www.tiktok.com/@{username}/live"
                message_sent = False
                role_applied = False

                # Process SPECIAL_USERS
                if username in SPECIAL_USERS:
                    for config in SPECIAL_USERS[username]:
                        server_id = config.get("server")
                        custom_message = config.get("message", "")
                        message = f"{custom_message} \n\U0001F517 Watch here: {tiktok_url}"
                        guild = bot.get_guild(int(server_id))

                        if guild:
                            print(f"[DEBUG] Found guild: {guild.name} ({guild.id}) for SPECIAL_USERS")

                            # Get announce channel
                            announce_channel_id = get_announce_channel(guild.id)
                            if announce_channel_id:
                                announce_channel = guild.get_channel(announce_channel_id)
                                if announce_channel:
                                    await announce_channel.send(message)
                                    message_sent = True
                                    print(f"[DEBUG] Announcement sent for {username} in channel {announce_channel.name}")
                            else:
                                await log_debug(f"[DEBUG] No announce channel found for guild {guild.id}")

                            # Apply role if configured
                            role_id = next(
                                (c.get("role_id") for c in SERVER_CONFIGS["production"] if str(guild.id) == c["guild_id"]),
                                None
                            )
                            if role_id:
                                role = get_role_by_id(guild, role_id)
                                if role:
                                    discord_id = USERNAME_TO_DISCORD_ID.get(username)
                                    if discord_id:
                                        member = guild.get_member(discord_id)
                                        if member:
                                            try:
                                                await member.add_roles(role)
                                                role_applied = True
                                                print(f"[DEBUG] Role '{role.name}' applied to Discord ID {discord_id} in guild {guild.name}.")
                                            except discord.Forbidden:
                                                print(f"[ERROR] Missing permissions to assign role '{role.name}' to Discord ID {discord_id}.")
                                        else:
                                            print(f"[DEBUG] Member with Discord ID {discord_id} not found in guild {guild.name}.")
                                    else:
                                        print(f"[DEBUG] No Discord ID mapped for TikTok username '{username}'.")
                                else:
                                    print(f"[DEBUG] Role ID '{role_id}' not found in guild {guild.name}.")
                            else:
                                print(f"[DEBUG] No role ID configured for guild {guild.id}.")

                # Handle no announcements or role applications
                if not message_sent:
                    print(f"[DEBUG] No announcement sent for {username}. Missing configuration or errors.")
                if not role_applied:
                    print(f"[DEBUG] No role applied for {username}. Missing configuration or errors.")

        except Exception as e:
            error_message = f"[ERROR] Error checking live status for {username}: {e}"
            print(error_message)
            await log_debug(error_message)

    print("Initial live status check complete.")

if __name__ == "__main__":
    bot.run(TOKEN)
