from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import config_manager


def build_help_embed() -> discord.Embed:
    """Builds the comprehensive Blood on the Clocktower Player & Storyteller resource embed."""
    embed = discord.Embed(
        title="🩸 Blood on the Clocktower — Player & Storyteller Guide",
        description=(
            "Welcome to **Ravenswood Bluff**! Below are official character sheets, "
            "core rules reminders, and how this Discord server handles Day & Night phases."
        ),
        color=discord.Color.brand_red(),
    )

    embed.add_field(
        name="📜 Official Base 3 Scripts & Almanacs",
        value=(
            "• [**Trouble Brewing** (Beginner — Character Sheet PDF)](https://bloodontheclocktower.com/custom-scripts) | "
            "[Wiki Almanac](https://wiki.bloodontheclocktower.com/Trouble_Brewing)\n"
            "• [**Bad Moon Rising** (Intermediate — Wiki Almanac)](https://wiki.bloodontheclocktower.com/Bad_Moon_Rising)\n"
            "• [**Sects & Violets** (Intermediate — Wiki Almanac)](https://wiki.bloodontheclocktower.com/Sects_%26_Violets)\n"
            "• [**Official BotC Wiki (Search Any Character)**](https://wiki.bloodontheclocktower.com/Main_Page)\n"
            "• [**Official Script Tool (Build / View Custom Scripts)**](https://script.bloodontheclocktower.com/)"
        ),
        inline=False,
    )

    embed.add_field(
        name="⚖️ Core Rules Quick Reference",
        value=(
            "• **Win Conditions:** **Good** wins by executing the Demon. **Evil** wins when only 2 players remain alive.\n"
            "• **Drunk vs. Poisoned:** You have *no ability* (and may receive false info from the Storyteller), "
            "even though you think your ability works normally.\n"
            "• **Nominations & Execution:** Each living player may nominate **once** per day; each player may be nominated **once** per day. "
            "Executing requires votes `>= 50%` of living players (and strictly more than the current highest vote count).\n"
            "• **Death & Ghost Votes:** Dead players lose their ability and cannot nominate, **but** they still talk, whisper, "
            "and have **1 Ghost Vote** for the rest of the game!"
        ),
        inline=False,
    )

    embed.add_field(
        name="🔊 How Discord Voice & Bot Commands Work",
        value=(
            "• **☀️ Day Phase:** Feel free to hop into any Whisper channel to chat privately. "
            "When the Day timer hits `0:00` (or the Storyteller presses **Gather to Town Square**), everyone is automatically pulled back to Town Square.\n"
            "• **🌙 Night Phase:** The Storyteller presses **Send to Cabins** (`/night`), moving every player to a private Cabin channel. "
            "Wait in your cabin—the Storyteller will hop in to visit you if your character wakes at night!\n"
            "• **🎛️ Storyteller Commands:** `/panel` (Interactive Dashboard), `/square`, `/night`, `/hush`, `/unhush`, `/visit`, `/timer start`, `/setup`."
        ),
        inline=False,
    )

    embed.set_footer(text="Tip: Storytellers can add [ST] to their nickname or use /panel for one-click controls.")
    return embed


class ResourcesCog(commands.Cog, name="Resources"):
    """Provides /help player resources and optional /setup channel utilities."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="help",
        description="📚 Display Blood on the Clocktower player resources, scripts, rules, and bot commands.",
    )
    @app_commands.describe(
        public="Post the help guide publicly in the channel so all players can read it (default: True)"
    )
    async def help_command(
        self,
        interaction: discord.Interaction,
        public: bool = True,
    ) -> None:
        embed = build_help_embed()
        await interaction.response.send_message(embed=embed, ephemeral=not public)

    # -------------------------------------------------------------------------
    # Setup Command Group (/setup status, /setup configure, /setup auto-create)
    # -------------------------------------------------------------------------

    setup_group = app_commands.Group(
        name="setup",
        description="⚙️ Inspect or customize how the bot detects your Town Square and Cabins.",
    )

    @setup_group.command(
        name="status",
        description="🔍 Check which channels and categories the bot currently auto-detects on this server.",
    )
    async def setup_status(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command must be used in a server.", ephemeral=True
            )
            return

        guild = interaction.guild
        cfg = config_manager.get(guild.id)

        town_square = config_manager.resolve_town_square(guild, interaction.user)
        day_cat = config_manager.resolve_day_category(guild, town_square)
        cabins_cat = config_manager.resolve_cabins_category(guild)
        alert_channel = config_manager.resolve_alert_channel(guild)
        current_st = guild.get_member(cfg.current_storyteller_id) if cfg.current_storyteller_id else None

        embed = discord.Embed(
            title="🔍 BotC Channel Detection Status",
            description=(
                "The bot uses **Zero-Config Auto-Discovery** by default, so you don't need to map every channel manually."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="🔊 Town Square Voice Channel",
            value=town_square.mention if town_square else "⚠️ *Not found yet (Join your Town Square channel or run `/setup configure`)*",
            inline=False,
        )
        embed.add_field(
            name="💬 General Text Channel (Timers & Alerts)",
            value=(
                alert_channel.mention
                if isinstance(alert_channel, discord.TextChannel)
                else "⚠️ *Uses the channel where the timer is started (Set via `/setup configure alert_channel:#channel`)*"
            ),
            inline=False,
        )
        embed.add_field(
            name="☀️ Day Category (Town Square + Whispers)",
            value=f"**{day_cat.name}** ({len(day_cat.voice_channels)} voice channels)" if day_cat else "⚠️ *Inferred once Town Square is detected*",
            inline=False,
        )
        embed.add_field(
            name="🌙 Cabins Category (Night Phase)",
            value=(
                f"**{cabins_cat.name}** ({len(cabins_cat.voice_channels)} existing cabins; temporary cabins created automatically as needed)"
                if cabins_cat
                else "✨ *Will be auto-created the first time you run `/night`*"
            ),
            inline=False,
        )
        embed.add_field(
            name="🎭 Active Storyteller Detection",
            value=(
                f"Currently tracked: {current_st.mention} *(auto-updates to whoever clicks `/panel` buttons or runs commands)*"
                if current_st
                else "Whoever clicks the `/panel` buttons or runs the command (plus anyone with `[ST]` in their nickname)"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @setup_group.command(
        name="configure",
        description="⚙️ Optional override: Set the Alert text channel, Town Square, or Categories.",
    )
    @app_commands.describe(
        alert_channel="Public text channel where Day timers and 1-minute warnings should be posted",
        town_square="The voice channel used as the Town Square",
        day_category="Category containing Town Square and Day Whisper voice channels",
        cabins_category="Category where Night Cabins are located (or created)",
    )
    async def setup_configure(
        self,
        interaction: discord.Interaction,
        alert_channel: Optional[discord.TextChannel] = None,
        town_square: Optional[discord.VoiceChannel] = None,
        day_category: Optional[discord.CategoryChannel] = None,
        cabins_category: Optional[discord.CategoryChannel] = None,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command must be used in a server.", ephemeral=True
            )
            return

        updates = {}
        if alert_channel is not None:
            updates["alert_channel_id"] = alert_channel.id
        if town_square is not None:
            updates["town_square_id"] = town_square.id
            if day_category is None and town_square.category_id:
                updates["day_category_id"] = town_square.category_id
        if day_category is not None:
            updates["day_category_id"] = day_category.id
        if cabins_category is not None:
            updates["cabins_category_id"] = cabins_category.id

        if not updates:
            await interaction.response.send_message(
                "ℹ️ No options provided. Use `/setup status` to inspect current settings.",
                ephemeral=True,
            )
            return

        config_manager.update(interaction.guild.id, **updates)
        await interaction.response.send_message(
            "✅ Saved custom server configuration! Run `/setup status` to review.",
            ephemeral=True,
        )

    @setup_group.command(
        name="auto-create",
        description="🏗️ Build (or link existing) BotC Day Category, Town Square, Whispers, and Cabins Category.",
    )
    @app_commands.describe(
        whisper_rooms="Number of daytime Whisper voice channels to ensure exist (default: 5)",
    )
    async def setup_auto_create(
        self,
        interaction: discord.Interaction,
        whisper_rooms: app_commands.Range[int, 1, 15] = 5,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command must be used in a server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        created_items: list[str] = []
        reused_items: list[str] = []

        try:
            # 1. Day Category (reuse if matching category exists)
            day_cat = discord.utils.find(
                lambda c: c.name.lower() in ("🕰️ botc - day", "botc - day")
                or ("botc" in c.name.lower() and "day" in c.name.lower()),
                guild.categories,
            )
            if day_cat is None:
                day_cat = await guild.create_category(
                    name="🕰️ BOTC - Day",
                    reason="BotC /setup auto-create",
                )
                created_items.append(f"Category **{day_cat.name}**")
            else:
                reused_items.append(f"Category **{day_cat.name}**")

            # 2. General Alert Text Channel (reuse if matching text channel exists in Day Category)
            chat_ch = discord.utils.find(
                lambda tc: "town-square-chat" in tc.name.lower()
                or "town-square" in tc.name.lower(),
                day_cat.text_channels,
            )
            if chat_ch is None:
                chat_ch = await guild.create_text_channel(
                    name="town-square-chat",
                    category=day_cat,
                    reason="BotC /setup auto-create",
                )
                created_items.append(f"Text {chat_ch.mention}")
            else:
                reused_items.append(f"Text {chat_ch.mention}")

            # 3. Town Square Voice Channel (reuse if matching voice channel exists)
            town_square = discord.utils.find(
                lambda vc: "town square" in vc.name.lower(),
                day_cat.voice_channels,
            ) or discord.utils.find(
                lambda vc: "town square" in vc.name.lower(),
                guild.voice_channels,
            )
            if town_square is None:
                town_square = await guild.create_voice_channel(
                    name="☀️ Town Square",
                    category=day_cat,
                    reason="BotC /setup auto-create",
                )
                created_items.append(f"Voice {town_square.mention}")
            else:
                reused_items.append(f"Voice {town_square.mention}")

            # 4. Whisper Voice Channels (only create missing ones up to whisper_rooms)
            created_whispers = 0
            reused_whispers = 0
            for i in range(1, whisper_rooms + 1):
                existing_w = discord.utils.find(
                    lambda vc, idx=i: f"whisper {idx}" in vc.name.lower(),
                    day_cat.voice_channels,
                )
                if existing_w is None:
                    await guild.create_voice_channel(
                        name=f"💬 Whisper {i}",
                        category=day_cat,
                        reason="BotC /setup auto-create",
                    )
                    created_whispers += 1
                else:
                    reused_whispers += 1

            if created_whispers:
                created_items.append(f"**{created_whispers}** Whisper channel(s)")
            if reused_whispers:
                reused_items.append(f"**{reused_whispers}** Whisper channel(s)")

            # 5. Cabins Category (reuse if matching category exists)
            cabins_cat = discord.utils.find(
                lambda c: c.name.lower() in ("🌙 botc - cabins", "botc - cabins")
                or ("cabin" in c.name.lower()),
                guild.categories,
            )
            if cabins_cat is None:
                cabins_cat = await guild.create_category(
                    name="🌙 BOTC - Cabins",
                    reason="BotC /setup auto-create",
                )
                created_items.append(f"Category **{cabins_cat.name}**")
            else:
                reused_items.append(f"Category **{cabins_cat.name}**")

            config_manager.update(
                guild.id,
                alert_channel_id=chat_ch.id,
                town_square_id=town_square.id,
                day_category_id=day_cat.id,
                cabins_category_id=cabins_cat.id,
            )

            summary_lines = ["✅ **BotC Setup Complete & Linked!**"]
            if reused_items:
                summary_lines.append(f"🔗 **Linked Existing:** {', '.join(reused_items)}")
            if created_items:
                summary_lines.append(f"✨ **Created New:** {', '.join(created_items)}")

            await interaction.followup.send("\n".join(summary_lines), ephemeral=True)
        except discord.HTTPException as exc:
            await interaction.followup.send(
                f"⚠️ Failed to create/link channels (check that the bot has **Manage Channels** permission): {exc}",
                ephemeral=True,
            )

    @setup_group.command(
        name="delete-auto",
        description="🗑️ Delete auto-generated BotC channels/categories by name match (temp cabins or full setup).",
    )
    @app_commands.describe(
        scope="Choose whether to delete only temporary Night Cabins or ALL auto-generated BotC channels & categories"
    )
    @app_commands.choices(
        scope=[
            app_commands.Choice(
                name="Only auto-generated Night Cabins (🔒 Cabin • ...)",
                value="cabins_only",
            ),
            app_commands.Choice(
                name="ALL auto-generated BotC channels & categories (Day, Whispers, Town Square, Cabins)",
                value="all",
            ),
        ]
    )
    async def setup_delete_auto(
        self,
        interaction: discord.Interaction,
        scope: str = "all",
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command must be used in a server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        deleted_channels = 0
        deleted_categories = 0

        try:
            # 1. Always delete auto-generated temporary Cabin channels matching name pattern
            for vc in list(guild.voice_channels):
                lower = vc.name.lower()
                is_temp_cabin = vc.name.startswith("🔒 Cabin •") or lower.startswith("cabin •")
                is_auto_day_vc = scope == "all" and (
                    vc.name == "☀️ Town Square"
                    or lower == "town square"
                    or vc.name.startswith("💬 Whisper ")
                    or lower.startswith("whisper ")
                )
                if is_temp_cabin or is_auto_day_vc:
                    # Don't delete the channel the interaction was somehow sent in
                    if interaction.channel and vc.id == interaction.channel.id:
                        continue
                    try:
                        await vc.delete(reason="BotC /setup delete-auto")
                        config_manager.unregister_temp_cabin(guild.id, vc.id)
                        deleted_channels += 1
                    except discord.HTTPException:
                        pass

            if scope == "all":
                # 2. Delete auto-generated town-square-chat text channel (unless the command was run inside it!)
                for tc in list(guild.text_channels):
                    if tc.name.lower() == "town-square-chat":
                        if interaction.channel and tc.id == interaction.channel.id:
                            continue
                        try:
                            await tc.delete(reason="BotC /setup delete-auto")
                            deleted_channels += 1
                        except discord.HTTPException:
                            pass

                # 3. Delete auto-generated categories if they are now empty (or match BotC auto names)
                for cat in list(guild.categories):
                    lower = cat.name.lower()
                    if lower in (
                        "🕰️ botc - day",
                        "botc - day",
                        "🌙 botc - cabins",
                        "botc - cabins",
                    ):
                        # Delete any remaining child channels inside those auto-created categories (except current channel)
                        for ch in list(cat.channels):
                            if interaction.channel and ch.id == interaction.channel.id:
                                continue
                            try:
                                await ch.delete(reason="BotC /setup delete-auto")
                                deleted_channels += 1
                            except discord.HTTPException:
                                pass

                        if len(cat.channels) == 0:
                            try:
                                await cat.delete(reason="BotC /setup delete-auto")
                                deleted_categories += 1
                            except discord.HTTPException:
                                pass

                config_manager.update(
                    guild.id,
                    town_square_id=None,
                    day_category_id=None,
                    cabins_category_id=None,
                    alert_channel_id=None,
                    temp_cabin_ids=[],
                )

            await interaction.followup.send(
                f"🗑️ Deleted **{deleted_channels}** auto-generated channel(s) and **{deleted_categories}** category(ies).",
                ephemeral=True,
            )
        except discord.HTTPException as exc:
            await interaction.followup.send(
                f"⚠️ Error while deleting auto-generated channels: {exc}",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ResourcesCog(bot))
