import asyncio
import discord
from discord.ext import commands
from TikTokLive import TikTokLiveClient
from TikTokLive.client.logger import LogLevel
from dotenv import load_dotenv
import os
import time
import json

# Load environment variables
load_dotenv()

# Bot token
TOKEN = os.getenv("TOKEN")

# List of TikTok usernames
TIKTOK_USERS = os.getenv("TIKTOK_USERS", "").split(',')

# Special users: Parse from the environment variables or an external JSON file
SPECIAL_USERS = {}
for key, value in os.environ.items():
    if key.startswith("SPECIAL_USERS_"):
        username = key.split("_", 2)[2]
        SPECIAL_USERS[username] = dict([msg.split(": ") for msg in value.split(",")])

# Update your server configs to handle multiple production servers and test server
SERVER_CONFIGS = {
    "production_1": {
        "guild_id": os.getenv("SERVER_CONFIG_1307019842410516573_GUILD_ID"),
        "announce_channel_id": os.getenv("SERVER_CONFIG_1307019842410516573_ANNOUNCE_CHANNEL_ID"),
        "role_name": os.getenv("SERVER_CONFIG_1307019842410516573_ROLE_NAME"),
        "owner_stream_channel_id": os.getenv("SERVER_CONFIG_1307019842410516573_OWNER_STREAM_CHANNEL_ID"),
        "owner_tiktok_username": os.getenv("SERVER_CONFIG_1307019842410516573_OWNER_TIKTOK_USERNAME")
    },
    "production_2": {
        "guild_id": os.getenv("SERVER_CONFIG_768792770734981141_GUILD_ID"),
        "announce_channel_id": os.getenv("SERVER_CONFIG_768792770734981141_ANNOUNCE_CHANNEL_ID"),
        "role_name": os.getenv("SERVER_CONFIG_768792770734981141_ROLE_NAME"),
        "owner_stream_channel_id": os.getenv("SERVER_CONFIG_768792770734981141_OWNER_STREAM_CHANNEL_ID"),
        "owner_tiktok_username": os.getenv("SERVER_CONFIG_768792770734981141_OWNER_TIKTOK_USERNAME")
    },
    "production_3": {
        "guild_id": os.getenv("SERVER_CONFIG_1145354259530010684_GUILD_ID"),
        "announce_channel_id": os.getenv("SERVER_CONFIG_1145354259530010684_ANNOUNCE_CHANNEL_ID"),
        "role_name": os.getenv("SERVER_CONFIG_1145354259530010684_ROLE_NAME"),
        "owner_stream_channel_id": os.getenv("SERVER_CONFIG_1145354259530010684_OWNER_STREAM_CHANNEL_ID"),
        "owner_tiktok_username": os.getenv("SERVER_CONFIG_1145354259530010684_OWNER_TIKTOK_USERNAME")
    },
    "test": {
        "guild_id": os.getenv("TEST_SERVER_GUILD_ID"),
        "announce_channel_id": os.getenv("TEST_SERVER_ANNOUNCE_CHANNEL_ID"),
        "role_name": os.getenv("TEST_SERVER_ROLE_NAME"),
        "owner_stream_channel_id": os.getenv("TEST_SERVER_OWNER_STREAM_CHANNEL_ID"),
        "owner_tiktok_username": os.getenv("TEST_SERVER_OWNER_TIKTOK_USERNAME"),
        "monitoring_started_channel_id": os.getenv("TEST_SERVER_MONITORING_STARTED_CHANNEL_ID")
    }
}

# Discord bot intents
intents = discord.Intents.default()
intents.guilds = True  # Allows bot to track guilds
intents.members = True  # Allows bot to track members (useful for role management)
intents.messages = True  # Allows bot to read messages (Message Content Intent)
intents.message_content = True  # Ensures the bot can access the content of messages

bot = commands.Bot(command_prefix="!", intents=intents)

# Setup logger with custom formatting
def setup_logger(logger):
    import logging

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

async def monitor_tiktok(user, client, server_config):
    guild_id = int(server_config.get("guild_id", 0))  # Handle missing guild_id
    announce_channel_id = server_config.get("announce_channel_id", 0)
    owner_stream_channel_id = server_config.get("owner_stream_channel_id", 0)
    owner_tiktok_username = server_config.get("owner_tiktok_username", "")
    role_name = server_config.get("role_name", "")

    guild = bot.get_guild(guild_id)
    if not guild:
        client.logger.error(f"Guild with ID {guild_id} not found.")
        return

    # Get the discord_user_id from environment variables
    discord_user_id = os.getenv(f"{user['tiktok_username']}_DISCORD_USER_ID")
    if not discord_user_id:
        client.logger.error(f"Discord user ID for {user['tiktok_username']} is missing.")
        return

    member = guild.get_member(int(discord_user_id))  # Use the ID to fetch the member
    if not member:
        client.logger.error(f"Discord member with ID {discord_user_id} not found.")
        return

    announce_channel = guild.get_channel(announce_channel_id)
    owner_channel = guild.get_channel(owner_stream_channel_id)

    setup_logger(client.logger)
    client.logger.info(f"Starting TikTok monitoring for {user['tiktok_username']}")

    while True:
        try:
            # Check if we have a cached live status
            live_status = live_status_cache.get(user['tiktok_username'], None)
            
            if live_status is None:
                # Fetch live status from TikTok if not cached
                live_status = await client.is_live()
                live_status_cache[user['tiktok_username']] = live_status

            if not live_status:
                client.logger.info(f"{user['tiktok_username']} is not live. Checking again in 60 seconds.")
                if role_name and role_name in [role.name for role in member.roles]:
                    role = discord.utils.get(guild.roles, name=role_name)
                    await member.remove_roles(role)
                    client.logger.info(f"Removed {role_name} role from {member.name}")
                await asyncio.sleep(60)
                continue

            # If the user is live and the status has changed, send messages and update roles
            if live_status:
                client.logger.info(f"{user['tiktok_username']} is live!")
                if role_name and role_name not in [role.name for role in member.roles]:
                    role = discord.utils.get(guild.roles, name=role_name)
                    await member.add_roles(role)
                    client.logger.info(f"Added {role_name} role to {member.name}")

                tiktok_url = f"https://www.tiktok.com/@{user['tiktok_username'].lstrip('@')}/live"
                server_messages = SPECIAL_USERS.get(
                    user["tiktok_username"],
                    f"\U0001F6D2 {user['tiktok_username']} is now live on TikTok! \n\U0001F534 **Watch live here:** {tiktok_url}"
                ).split(",")

                # Send announcement messages
                if announce_channel:
                    await announce_channel.send(server_messages)
                    client.logger.info(f"Announced live stream for {user['tiktok_username']} in channel {announce_channel.name}")

                if user["tiktok_username"] == owner_tiktok_username and owner_channel:
                    await owner_channel.send(f"\U0001F534 {user['tiktok_username']} is now live on TikTok! \n\U0001F517 Watch live: {tiktok_url}")
                    client.logger.info(f"Notified owner channel for {user['tiktok_username']}")

                live_status_cache[user['tiktok_username']] = True

            await asyncio.sleep(60)

        except Exception as e:
            client.logger.error(f"Error monitoring {user['tiktok_username']}: {e}")
            await asyncio.sleep(60)

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")

    environment = os.getenv("ENVIRONMENT", "test")  # Get environment type (production or test)
    if environment == "production":
        # Loop through all production servers
        for key, server_config in SERVER_CONFIGS.items():
            if key.startswith("production"):
                try:
                    guild_id = server_config.get("guild_id")
                    if not guild_id:
                        print(f"Warning: guild_id is missing or invalid for server {key}. Skipping this entry.")
                        continue
                    
                    # Attempt to get the guild and check if it's valid
                    int_server_id = int(guild_id)  # Convert to integer
                    guild = bot.get_guild(int_server_id)
                    if not guild:
                        print(f"Warning: Guild with ID {guild_id} not found for server {key}. Skipping.")
                        continue

                    # Proceed with monitoring for TikTok users
                    for user in TIKTOK_USERS:
                        user_info = {
                            "tiktok_username": user,
                            "discord_username": os.getenv(f"{user}_DISCORD_USERNAME")  # Get Discord username from env
                        }
                        client = TikTokLiveClient(unique_id=user)
                        setup_logger(client.logger)
                        asyncio.create_task(monitor_tiktok(user_info, client, server_config))
                        
                except ValueError as e:
                    print(f"Warning: Invalid server_id {guild_id} for server {key}. Skipping this entry.")
                    continue
    else:
        # Handle Test Server Configuration
        server_config = SERVER_CONFIGS.get("test")
        try:
            guild_id = server_config.get("guild_id")
            if not guild_id:
                print(f"Warning: guild_id is missing or invalid for test server. Skipping this entry.")
                return

            int_server_id = int(guild_id)
            guild = bot.get_guild(int_server_id)
            if not guild:
                print(f"Warning: Guild with ID {guild_id} not found for test server. Skipping.")
                return

            # Send a message to the test server indicating the monitoring has started
            monitoring_started_channel_id = server_config.get("monitoring_started_channel_id")
            if monitoring_started_channel_id:
                test_channel = guild.get_channel(int(monitoring_started_channel_id))
                if test_channel:
                    await test_channel.send("🔔 Monitoring of TikTok streams has started! 🔔")
                else:
                    print(f"Test channel {monitoring_started_channel_id} not found.")
            
            # Proceed with TikTok user monitoring for the test server
            for user in TIKTOK_USERS:
                user_info = {
                    "tiktok_username": user,
                    "discord_username": os.getenv(f"{user}_DISCORD_USERNAME")
                }
                client = TikTokLiveClient(unique_id=user)
                setup_logger(client.logger)
                asyncio.create_task(monitor_tiktok(user_info, client, server_config))

        except ValueError as e:
            print(f"Error: Invalid server ID for test server. {e}")
            return  # Skip invalid server IDs


@bot.command()
async def ping(ctx):
    """Simple ping command to check if the bot is online"""
    await ctx.send("Pong!")

@bot.command()
async def check_live(ctx, tiktok_username: str):
    """Check if a specific TikTok user is live"""
    client = TikTokLiveClient(unique_id=tiktok_username)
    live_status = await client.is_live()
    if live_status:
        await ctx.send(f"{tiktok_username} is live!")
    else:
        await ctx.send(f"{tiktok_username} is not live.")

@bot.command()
async def force_announce(ctx, tiktok_username: str):
    """Force an announcement of a TikTok user's live stream"""
    announce_channel_id = 1317209936933158997  # Replace with your channel ID
    tiktok_url = f"https://www.tiktok.com/@{tiktok_username}/live"
    message = f"🚨 {tiktok_username} is now live on TikTok! 🚨\n🔴 Watch live here: {tiktok_url}"

    announce_channel = bot.get_channel(announce_channel_id)
    if announce_channel:
        await announce_channel.send(message)
        await ctx.send(f"Announcement sent for {tiktok_username}!")
    else:
        await ctx.send("Announce channel not found!")

@bot.command()
async def status(ctx):
    """Check the bot's current status"""
    await ctx.send(f"Bot is online as {bot.user}. Monitoring {len(TIKTOK_USERS)} TikTok users.")

@bot.event
async def on_command_error(ctx, error):
    print(f"Error occurred: {error}")


if __name__ == "__main__":
    bot.run(TOKEN)
