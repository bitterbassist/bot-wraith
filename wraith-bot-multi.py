import asyncio
import discord
from discord.ext import commands
from TikTokLive import TikTokLiveClient
from TikTokLive.client.logger import LogLevel
from dotenv import load_dotenv
import os
import ast

# Load environment variables
load_dotenv()

# Bot token
TOKEN = os.getenv("TOKEN")

# Server-specific TikTok users
TIKTOK_USERS = ast.literal_eval(os.getenv("TIKTOK_USERS", "{}"))

# Users with custom messages per server
SPECIAL_USERS = ast.literal_eval(os.getenv("SPECIAL_USERS", "{}"))

# Server-specific configurations
server_configs = ast.literal_eval(os.getenv("SERVER_CONFIGS", "{}"))

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

async def monitor_tiktok(user, client, guild_config):
    guild_id = guild_config.get("guild_id")
    announce_channel_id = guild_config.get("announce_channel_id")
    owner_stream_channel_id = guild_config.get("owner_stream_channel_id")
    owner_tiktok_username = guild_config.get("owner_tiktok_username")
    role_name = guild_config.get("role_name")

    guild = discord.utils.get(bot.guilds, id=guild_id)
    role = discord.utils.get(guild.roles, name=role_name)
    member = discord.utils.get(guild.members, name=user["discord_username"])
    announce_channel = discord.utils.get(guild.text_channels, id=announce_channel_id)
    owner_channel = discord.utils.get(guild.text_channels, id=owner_stream_channel_id)

    live_status = False

    client.logger.setLevel(LogLevel.INFO.value)

    while True:
        try:
            if not await client.is_live():
                client.logger.info(f"{user['tiktok_username']} is not live. Checking again in 60 seconds.")
                if role in member.roles:
                    await member.remove_roles(role)
                    client.logger.info(f"Removed {role_name} role from {member.name}")
                live_status = False
                await asyncio.sleep(60)
            else:
                client.logger.info(f"{user['tiktok_username']} is live!")
                if role not in member.roles:
                    await member.add_roles(role)
                    client.logger.info(f"Added {role_name} role to {member.name}")
                if not live_status:
                    tiktok_url = f"https://www.tiktok.com/@{user['tiktok_username'].lstrip('@')}/live"
                    server_messages = SPECIAL_USERS.get(str(guild_id), {})
                    message = server_messages.get(
                        user["tiktok_username"],
                        f"\U0001F6D2 {user['tiktok_username']} is now live on TikTok! \n\U0001F534 **Watch live here:** {tiktok_url}"
                    )
                    try:
                        metadata = await client.get_live_metadata()
                        if metadata:
                            message += f"\n\U0001F4E2 Title: {metadata.get('title', 'Untitled')}\n\U0001F465 Viewers: {metadata.get('viewer_count', 'N/A')}"
                    except Exception as e:
                        client.logger.warning(f"Could not fetch metadata for {user['tiktok_username']}: {e}")

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
    for guild_id, users in TIKTOK_USERS.items():
        for user in users:
            client = TikTokLiveClient(unique_id=user["tiktok_username"])
            asyncio.create_task(monitor_tiktok(
                user,
                client,
                {**server_configs[guild_id], "guild_id": int(guild_id)}
            ))

if __name__ == "__main__":
    bot.run(TOKEN)
