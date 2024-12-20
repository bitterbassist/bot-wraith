import asyncio
import discord
from discord.ext import commands
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent
from dotenv import load_dotenv
import os
import logging

# Load environment variables
load_dotenv()

# Bot token
TOKEN = os.getenv("TOKEN")

# List of TikTok usernames
TIKTOK_USERS = os.getenv("TIKTOK_USERS", "").split(',')

# Map TikTok usernames to Discord user IDs
USERNAME_TO_DISCORD_ID = {
    pair.split(":")[0]: int(pair.split(":")[1])
    for pair in os.getenv("USERNAME_TO_DISCORD_ID", "").split(",")
    if ":" in pair
}

# Discord configurations
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")
if not DISCORD_GUILD_ID:
    raise ValueError("DISCORD_GUILD_ID is not set in the environment variables.")
DISCORD_GUILD_ID = int(DISCORD_GUILD_ID)

DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
if not DISCORD_CHANNEL_ID:
    raise ValueError("DISCORD_CHANNEL_ID is not set in the environment variables.")
DISCORD_CHANNEL_ID = int(DISCORD_CHANNEL_ID)

ROLE_NAME = os.getenv("ROLE_NAME", "Live Now")

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

# Initialize TikTok clients
clients = {}

def create_tiktok_client(username):
    client = TikTokLiveClient(unique_id=username)

    @client.on(ConnectEvent)
    async def on_connect(event):
        print(f"[INFO] {username} started a live stream.")

        # Assign role and send announcement in Discord
        guild = bot.get_guild(DISCORD_GUILD_ID)
        role = discord.utils.get(guild.roles, name=ROLE_NAME)
        discord_id = USERNAME_TO_DISCORD_ID.get(username)
        if discord_id:
            member = guild.get_member(discord_id)
            if member and role:
                await member.add_roles(role)
                channel = bot.get_channel(DISCORD_CHANNEL_ID)
                await channel.send(f"{member.mention} is now live on TikTok! Watch here: https://www.tiktok.com/@{username}/live")

    @client.on(DisconnectEvent)
    async def on_disconnect(event):
        print(f"[INFO] {username} ended the live stream.")

        # Remove role in Discord
        guild = bot.get_guild(DISCORD_GUILD_ID)
        role = discord.utils.get(guild.roles, name=ROLE_NAME)
        discord_id = USERNAME_TO_DISCORD_ID.get(username)
        if discord_id:
            member = guild.get_member(discord_id)
            if member and role:
                await member.remove_roles(role)
                channel = bot.get_channel(DISCORD_CHANNEL_ID)
                await channel.send(f"{member.mention} has ended their TikTok live stream.")

    return client

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")

    # Initialize TikTok clients
    for username in TIKTOK_USERS:
        if username.strip():
            clients[username] = create_tiktok_client(username)
            clients[username].run()

if __name__ == "__main__":
    bot.run(TOKEN)
