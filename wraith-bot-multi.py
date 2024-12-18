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

# Map TikTok usernames to Discord usernames
USERNAME_MAP = {
    pair.split(":")[0]: pair.split(":")[1]
    for pair in os.getenv("USERNAME_MAP", "").split(",")
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
            results.append(f"{username} is {'live' if live_status else 'not live'}")
        except Exception as e:
            results.append(f"{username}: Error - {e}")

    designated_channel_id = int(os.getenv("DESIGNATED_CHANNEL_ID"))
    designated_channel = bot.get_channel(designated_channel_id)
    if designated_channel:
        await designated_channel.send("\n".join(results) if results else "No monitored users.")
    else:
        await ctx.send("Designated channel not found.")

@bot.command()
async def bot_status(ctx):
    """Display the bot's current status."""
    designated_channel_id = int(os.getenv("DESIGNATED_CHANNEL_ID"))
    designated_channel = bot.get_channel(designated_channel_id)
    if designated_channel:
        await designated_channel.send("Bot is online and monitoring TikTok users! 🚀")
    else:
        await ctx.send("Designated channel not found.")

@bot.command()
async def test_post_all(ctx):
    """Send a test message to all announcement channels."""
    test_message = "🚨 This is a test announcement from Wraith Bot. All systems are functioning correctly! 🚨"
    errors = []

    for server_config in SERVER_CONFIGS["production"]:
        guild_id = server_config.get("guild_id")
        announce_channel_id = server_config.get("announce_channel_id")
        if not guild_id or not announce_channel_id:
            errors.append(f"Missing configuration for server {guild_id}")
            continue

        guild = bot.get_guild(int(guild_id))
        if not guild:
            errors.append(f"Guild with ID {guild_id} not found.")
            continue

        announce_channel = guild.get_channel(int(announce_channel_id))
        if not announce_channel:
            errors.append(f"Announcement channel {announce_channel_id} not found in guild {guild.name}.")
            continue

        try:
            await announce_channel.send(test_message)
            print(f"[DEBUG] Test message sent to {announce_channel.name} in guild {guild.name}")
        except Exception as e:
            errors.append(f"Failed to send message to {announce_channel_id} in guild {guild.name}: {e}")

    if errors:
        await ctx.send("Some errors occurred:\n" + "\n".join(errors))
    else:
        await ctx.send("Test message successfully sent to all announcement channels!")

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
                            announce_channel_id = next(
                                (c.get("announce_channel_id") for c in SERVER_CONFIGS["production"] if c["guild_id"] == str(guild.id)),
                                None
                            )
                            if announce_channel_id:
                                announce_channel = guild.get_channel(int(announce_channel_id))
                                if announce_channel:
                                    await announce_channel.send(message)
                                    message_sent = True
                                    print(f"[DEBUG] Announcement sent for {username} in channel {announce_channel.name}")
                            else:
                                print(f"[DEBUG] No announce channel found for guild {guild.id}")

                            # Apply role if configured
                            role_name = next(
                                (c.get("role_name") for c in SERVER_CONFIGS["production"] if c["guild_id"] == str(guild.id)),
                                None
                            )
                            if role_name:
                                role = discord.utils.get(guild.roles, name=role_name)
                                mapped_username = USERNAME_MAP.get(username, username)
                                member = discord.utils.find(lambda m: m.name == mapped_username, guild.members)
                                if role and member:
                                    try:
                                        await member.add_roles(role)
                                        role_applied = True
                                        print(f"[DEBUG] Role '{role.name}' applied to {mapped_username} in guild {guild.name}.")
                                    except discord.Forbidden:
                                        print(f"[ERROR] Missing permissions to assign role '{role.name}' to {mapped_username}.")
                                else:
                                    print(f"[DEBUG] Role or member not found for {username} in guild {guild.name}.")
                        else:
                            print(f"[DEBUG] Guild not found for server_id: {server_id}")

                # Process VIP_USERS
                if username in VIP_USERS:
                    for config in VIP_USERS[username]:
                        server_id = config.get("server", "")
                        custom_message = config.get("message", "")
                        message = f"{custom_message} \n\U0001F517 Watch here: {tiktok_url}"
                        guild = bot.get_guild(int(server_id)) if server_id else None

                        if guild:
                            print(f"[DEBUG] Found guild: {guild.name} ({guild.id}) for VIP_USERS")
                            announce_channel_id = next(
                                (c.get("announce_channel_id") for c in SERVER_CONFIGS["production"] if c["guild_id"] == str(guild.id)),
                                None
                            )
                            if announce_channel_id:
                                announce_channel = guild.get_channel(int(announce_channel_id))
                                if announce_channel:
                                    await announce_channel.send(message)
                                    message_sent = True
                                    print(f"[DEBUG] Announcement sent for {username} in channel {announce_channel.name}")
                            else:
                                print(f"[DEBUG] No announce channel found for guild {guild.id}")

                            # Apply role if configured
                            role_name = next(
                                (c.get("role_name") for c in SERVER_CONFIGS["production"] if c["guild_id"] == str(guild.id)),
                                None
                            )
                            if role_name:
                                role = discord.utils.get(guild.roles, name=role_name)
                                mapped_username = USERNAME_MAP.get(username, username)
                                member = discord.utils.find(lambda m: m.name == mapped_username, guild.members)
                                if role and member:
                                    try:
                                        await member.add_roles(role)
                                        role_applied = True
                                        print(f"[DEBUG] Role '{role.name}' applied to {mapped_username} in guild {guild.name}.")
                                    except discord.Forbidden:
                                        print(f"[ERROR] Missing permissions to assign role '{role.name}' to {mapped_username}.")
                                else:
                                    print(f"[DEBUG] Role or member not found for {username} in guild {guild.name}.")
                        else:
                            print(f"[DEBUG] Guild not found for server_id: {server_id}")

                if not message_sent:
                    print(f"[DEBUG] No announcement sent for {username}. Missing configuration or errors.")
                if not role_applied:
                    print(f"[DEBUG] No role applied for {username}. Missing configuration or errors.")

        except Exception as e:
            error_message = f"[ERROR] Error checking live status for {username}: {e}"
            print(error_message)
            await send_debug_logs_to_channel(error_message)

    print("Initial live status check complete.")

if __name__ == "__main__":
    bot.run(TOKEN)
