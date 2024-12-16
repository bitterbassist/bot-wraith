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
for key, value in os.environ.items():
    if key.startswith("SPECIAL_USERS_"):
        username = key.split("_", 2)[2]
        try:
            SPECIAL_USERS[username] = {
                key_value[0]: key_value[1]
                for msg in value.split(",")
                if len(key_value := msg.split(": ")) == 2
            }
        except Exception as e:
            print(f"Error processing special user {username}: {value}. Error: {e}")

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

async def monitor_tiktok(user, client, server_config, environment):
    guild_id = int(server_config.get("guild_id", 0))  # Handle missing guild_id
    announce_channel_id = server_config.get("announce_channel_id", 0)
    owner_stream_channel_id = server_config.get("owner_stream_channel_id", 0)
    owner_tiktok_username = server_config.get("owner_tiktok_username", "")
    role_name = server_config.get("role_name", "")

    guild = bot.get_guild(guild_id)
    if not guild:
        client.logger.error(f"Guild with ID {guild_id} not found in {environment} environment.")
        return

    # Get the discord_username from environment variables
    discord_username = os.getenv(f"{user['tiktok_username']}_DISCORD_USERNAME")
    if not discord_username:
        client.logger.error(f"Discord username for {user['tiktok_username']} is missing in {environment}.")
        return

    # Search for members by username (ignoring discriminator)
    matching_members = [
        member for member in guild.members if member.name.lower() == discord_username.lower()
    ]
    if not matching_members:
        client.logger.error(f"No members with username '{discord_username}' found in {environment}.")
        return
    elif len(matching_members) > 1:
        client.logger.warning(f"Multiple members with username '{discord_username}' found. Using the first match.")

    member = matching_members[0]
    announce_channel = guild.get_channel(int(announce_channel_id))
    owner_channel = guild.get_channel(int(owner_stream_channel_id))

    setup_logger(client.logger)
    client.logger.info(f"Starting TikTok monitoring for {user['tiktok_username']} in {environment}.")

    while True:
        try:
            # Check if we have a cached live status
            live_status = live_status_cache.get(user['tiktok_username'], None)

            if live_status is None:
                # Fetch live status from TikTok if not cached
                live_status = await client.is_live()
                live_status_cache[user['tiktok_username']] = live_status

            if not live_status:
                client.logger.info(f"{user['tiktok_username']} is not live in {environment}. Checking again in 60 seconds.")
                if role_name and role_name in [role.name for role in member.roles]:
                    role = discord.utils.get(guild.roles, name=role_name)
                    await member.remove_roles(role)
                    client.logger.info(f"Removed {role_name} role from {member.name} in {environment}.")
                await asyncio.sleep(60)
                continue

            # If the user is live and the status has changed, send messages and update roles
            if live_status:
                client.logger.info(f"{user['tiktok_username']} is live in {environment}!")
                if role_name and role_name not in [role.name for role in member.roles]:
                    role = discord.utils.get(guild.roles, name=role_name)
                    await member.add_roles(role)
                    client.logger.info(f"Added {role_name} role to {member.name} in {environment}.")

                tiktok_url = f"https://www.tiktok.com/@{user['tiktok_username'].lstrip('@')}/live"
                server_messages = SPECIAL_USERS.get(
                    user["tiktok_username"],
                    f"\U0001F6D2 {user['tiktok_username']} is now live on TikTok! \n\U0001F534 **Watch live here:** {tiktok_url}"
                ).split(",")

                # Send announcement messages
                if announce_channel:
                    await announce_channel.send(server_messages)
                    client.logger.info(f"Announced live stream for {user['tiktok_username']} in channel {announce_channel.name} ({environment}).")

                if user["tiktok_username"] == owner_tiktok_username and owner_channel:
                    await owner_channel.send(f"\U0001F534 {user['tiktok_username']} is now live on TikTok! \n\U0001F517 Watch live: {tiktok_url}")
                    client.logger.info(f"Notified owner channel for {user['tiktok_username']} ({environment}).")

                live_status_cache[user['tiktok_username']] = True

            await asyncio.sleep(60)

        except Exception as e:
            client.logger.error(f"Error monitoring {user['tiktok_username']} in {environment}: {e}")
            await asyncio.sleep(60)

# Updated on_ready function to exclude error logging for the test server
@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")

    # Set the custom status for the bot
    await bot.change_presence(
        activity=discord.Game(name="Doing Wraith Bot Stuff")  # Custom status message
    )

    # Iterate through the server configurations
    for environment, server_configs in SERVER_CONFIGS.items():
        try:
            # If the environment is "production", server_configs is a list
            # If the environment is "test", server_configs is a dictionary
            if isinstance(server_configs, list):
                for server_config in server_configs:
                    guild_id = server_config.get('guild_id')
                    if not guild_id:
                        # Skip test server warnings
                        if environment == "test":
                            continue

                        print(f"Warning: guild_id is missing or invalid for {environment} environment. Skipping.")
                        continue

                    int_server_id = int(guild_id)  # Convert guild_id to integer

                    # Send a message to the test server indicating the monitoring has started
                    if environment == "test":
                        monitoring_started_channel_id = server_config.get("monitoring_started_channel_id")
                        if monitoring_started_channel_id:
                            test_guild = bot.get_guild(int_server_id)
                            test_channel = test_guild.get_channel(int(monitoring_started_channel_id))
                            if test_channel:
                                await test_channel.send("\U0001F514 Monitoring of TikTok streams has started! \U0001F514")

                    # Proceed with the monitoring for TikTok users
                    for user in TIKTOK_USERS:
                        user_info = {
                            "tiktok_username": user,
                            "discord_username": os.getenv(f"{user}_DISCORD_USERNAME")  # Still using this for reference
                        }
                        client = TikTokLiveClient(unique_id=user)
                        setup_logger(client.logger)
                        asyncio.create_task(monitor_tiktok(user_info, client, server_config, environment))

            elif isinstance(server_configs, dict):
                # Handle the "test" environment
                server_config = server_configs
                guild_id = server_config.get('guild_id')
                if not guild_id:
                    print(f"Warning: guild_id is missing or invalid for {environment} environment. Skipping.")
                    continue

                int_server_id = int(guild_id)  # Convert guild_id to integer

                # Send a message to the test server indicating the monitoring has started
                monitoring_started_channel_id = server_config.get("monitoring_started_channel_id")
                if monitoring_started_channel_id:
                    test_guild = bot.get_guild(int_server_id)
                    test_channel = test_guild.get_channel(int(monitoring_started_channel_id))
                    if test_channel:
                        await test_channel.send("\U0001F514 Monitoring of TikTok streams has started! \U0001F514")

                # Proceed with the monitoring for TikTok users
                for user in TIKTOK_USERS:
                    user_info = {
                        "tiktok_username": user,
                        "discord_username": os.getenv(f"{user}_DISCORD_USERNAME")  # Still using this for reference
                    }
                    client = TikTokLiveClient(unique_id=user)
                    setup_logger(client.logger)
                    asyncio.create_task(monitor_tiktok(user_info, client, server_config, environment))

        except ValueError as e:
            # Skip test server warnings
            if environment == "test":
                continue
            print(f"Error: Invalid server ID for {server_config['guild_id']}. {e}")
            continue  # Skip invalid server IDs

@bot.command()
async def ping(ctx):
    """Simple ping command to check if the bot is online"""
    await ctx.send("Pong!")

@bot.command()
async def bot_status(ctx):
    """Tells you that the bot is online in all servers"""
    online_guilds = [guild.name for guild in bot.guilds]  # List all guild names
    if online_guilds:
        await ctx.send(f"Bot is online in the following Discord servers:\n" + "\n".join(online_guilds))
    else:
        await ctx.send("Bot is not currently in any Discord servers.")

@bot.command()
async def test_post(ctx):
    """Send a test message to specific channels by ID across all servers."""
    test_message = "🚨 This is a test announcement! The wonderful people at Revenant Studios sent this message to ensure that your bot is online and functioning. This may also include bot updates and patches. We thank you for using Wraith Bot! 🚨"

    # Predefined list of channel IDs (as integers, not names)
    target_channel_ids = [
        1209176431968653442,  # BarryAllen Self-Promote
        1306652093037285386,  # Pickle Squad Self=promoting
        1308455912876282006,  # Sykk Shadows tik-tik-self-promo
        1317731202026700882,  # wraith=bot-monitoring
    ]
    
    # Iterate through all guilds the bot is connected to
    for guild in bot.guilds:
        # Iterate through each text channel in the guild
        for channel in guild.text_channels:
            # Check if the channel's ID is in the list of target IDs
            if channel.id in target_channel_ids:
                try:
                    # Send the test message to the channel
                    await channel.send(test_message)
                    print(f"Test message sent to {channel.name} in {guild.name}")
                except Exception as e:
                    print(f"Failed to send message to {channel.name} in {guild.name}: {e}")
                    continue
    
    await ctx.send("Test message sent to the specified channels.")

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
    message = f"\U0001F6A8 {tiktok_username} is now live on TikTok! \U0001F6A8\n\U0001F534 Watch live here: {tiktok_url}"

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
