import asyncio
import discord
from discord.ext import commands
from TikTokLive import TikTokLiveClient
from TikTokLive.client.logger import LogLevel
from dotenv import load_dotenv
import os
import json  # Added import for json

# Load environment variables
load_dotenv()

# Bot token
TOKEN = os.getenv("TOKEN")

# Parse TIKTOK_USERS from environment variable and convert it back to a dictionary
TIKTOK_USERS = json.loads(os.getenv("TIKTOK_USERS", "{}"))

# Parse SPECIAL_USERS from environment variable and convert it back to a dictionary
SPECIAL_USERS = json.loads(os.getenv("SPECIAL_USERS", "{}"))

# Parse SERVER_CONFIGS from environment variable and convert it back to a dictionary
SERVER_CONFIGS = json.loads(os.getenv("SERVER_CONFIGS", "{}"))

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

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

async def monitor_tiktok(user, client, guild_config):
    guild_id = int(guild_config.get("guild_id", 0))  # Handle missing guild_id
    announce_channel_id = guild_config.get("announce_channel_id", 0)
    owner_stream_channel_id = guild_config.get("owner_stream_channel_id", 0)
    owner_tiktok_username = guild_config.get("owner_tiktok_username", "")
    role_name = guild_config.get("role_name", "")

    guild = bot.get_guild(guild_id)
    if not guild:
        client.logger.error(f"Guild with ID {guild_id} not found.")
        return

    role = discord.utils.get(guild.roles, name=role_name)
    member = guild.get_member_named(user["discord_username"])
    announce_channel = guild.get_channel(announce_channel_id)
    owner_channel = guild.get_channel(owner_stream_channel_id)

    live_status = False

    setup_logger(client.logger)
    client.logger.info(f"Starting TikTok monitoring for {user['tiktok_username']}")

    while True:
        try:
            if not await client.is_live():
                client.logger.info(f"{user['tiktok_username']} is not live. Checking again in 60 seconds.")
                if role and role in member.roles:
                    await member.remove_roles(role)
                    client.logger.info(f"Removed {role_name} role from {member.name}")
                live_status = False
                await asyncio.sleep(60)
            else:
                client.logger.info(f"{user['tiktok_username']} is live!")
                if role and role not in member.roles:
                    await member.add_roles(role)
                    client.logger.info(f"Added {role_name} role to {member.name}")
                if not live_status:
                    tiktok_url = f"https://www.tiktok.com/@{user['tiktok_username'].lstrip('@')}/live"
                    server_messages = SPECIAL_USERS.get(
                        user["tiktok_username"],
                        f"\U0001F6D2 {user['tiktok_username']} is now live on TikTok! \n\U0001F534 **Watch live here:** {tiktok_url}"
                    ).split(",")
                    
                    message = server_messages
                    try:
                        metadata = await client.get_live_metadata()
                        if metadata:
                            message += [f"\n\U0001F4E2 Title: {metadata.get('title', 'Untitled')}\n\U0001F465 Viewers: {metadata.get('viewer_count', 'N/A')}"]
                    except Exception as e:
                        client.logger.warning(f"Could not fetch metadata for {user['tiktok_username']}: {e}")

                    if announce_channel:
                        await announce_channel.send(message)
                        client.logger.info(f"Announced live stream for {user['tiktok_username']} in channel {announce_channel.name}")

                    if user["tiktok_username"] == owner_tiktok_username and owner_channel:
                        await owner_channel.send(f"\U0001F534 {user['tiktok_username']} is now live on TikTok! \n\U0001F517 Watch live: {tiktok_url}")
                        client.logger.info(f"Notified owner channel for {user['tiktok_username']}")

                    live_status = True
                await asyncio.sleep(60)
        except Exception as e:
            client.logger.error(f"Error monitoring {user['tiktok_username']}: {e}")
            await asyncio.sleep(60)

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    for guild_id in SERVER_CONFIGS:
        guild_config = SERVER_CONFIGS[guild_id]
        for user in TIKTOK_USERS:
            user_info = {
                "tiktok_username": user,
                "discord_username": os.getenv(f"{user}_DISCORD_USERNAME")
            }
            client = TikTokLiveClient(unique_id=user)
            setup_logger(client.logger)
            asyncio.create_task(monitor_tiktok(
                user_info,
                client,
                {**guild_config, "guild_id": int(guild_id)}
            ))

# Testing Commands

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
    announce_channel_id = 1234567890  # Replace with your channel ID
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

if __name__ == "__main__":
    bot.run(TOKEN)
