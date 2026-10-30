from __future__ import annotations

import logging
import os
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("clocktower_bot")

COGS = (
    "cogs.movement",
    "cogs.timer",
    "cogs.resources",
    "cogs.panel",
)


class ClocktowerBot(commands.Bot):
    """Discord Storyteller Assistant Bot for Blood on the Clocktower."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        intents.members = True

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self) -> None:
        for ext in COGS:
            await self.load_extension(ext)
            logger.info("Loaded extension: %s", ext)

        guild_id_raw = os.getenv("DISCORD_GUILD_ID", "").strip()
        if guild_id_raw.isdigit():
            guild_obj = discord.Object(id=int(guild_id_raw))
            self.tree.copy_global_to(guild=guild_obj)
            synced = await self.tree.sync(guild=guild_obj)
            logger.info(
                "Synced %d slash command(s) to development guild ID %s",
                len(synced),
                guild_id_raw,
            )
            # Clear global commands so they don't appear twice alongside guild-specific commands
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            logger.info("Cleared global slash commands to prevent duplicate autocomplete entries")
        else:
            synced = await self.tree.sync()
            logger.info("Synced %d global slash command(s)", len(synced))

    async def on_ready(self) -> None:
        if self.user:
            logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Ravenswood Bluff • /panel | /help",
            )
        )


def main() -> None:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token or token == "your_discord_bot_token_here":
        logger.error(
            "Missing DISCORD_TOKEN! Copy .env.example to .env and add your bot token."
        )
        sys.exit(1)

    bot = ClocktowerBot()
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
