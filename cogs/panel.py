from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs.resources import build_help_embed
from config import config_manager


class VisitPlayerSelect(discord.ui.Select):
    """Dropdown selector allowing the Storyteller to jump directly into a player's voice channel."""

    def __init__(self, options: list[discord.SelectOption]) -> None:
        super().__init__(
            placeholder="🧭 Choose a player to visit in their cabin/channel...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "⚠️ Connect to any voice channel first so Discord lets me move you!",
                ephemeral=True,
            )
            return

        target_member_id = int(self.values[0])
        target_member = interaction.guild.get_member(target_member_id)
        if not target_member or not target_member.voice or not isinstance(target_member.voice.channel, discord.VoiceChannel):
            await interaction.response.send_message(
                "⚠️ That player is no longer in a voice channel.",
                ephemeral=True,
            )
            return

        try:
            await interaction.user.move_to(
                target_member.voice.channel,
                reason=f"BotC Panel: Visiting {target_member.display_name}",
            )
            await interaction.response.send_message(
                f"🧭 Moved you into **{target_member.voice.channel.name}** with **{target_member.display_name}**.",
                ephemeral=True,
            )
        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"⚠️ Could not move you: {exc}", ephemeral=True
            )


class VisitPlayerView(discord.ui.View):
    def __init__(self, options: list[discord.SelectOption]) -> None:
        super().__init__(timeout=120)
        self.add_item(VisitPlayerSelect(options))


class StorytellerPanelView(discord.ui.View):
    """Persistent Storyteller Control Panel with buttons for Day/Night movement, Timers, and Utilities."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    # -------------------------------------------------------------------------
    # Row 0: Phase & Voice Movement Controls
    # -------------------------------------------------------------------------

    @discord.ui.button(
        label="Gather to Town Square",
        emoji="☀️",
        style=discord.ButtonStyle.success,
        custom_id="botc:panel:square",
        row=0,
    )
    async def btn_square(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        movement_cog = self.bot.get_cog("Movement")
        if movement_cog is None:
            await interaction.response.send_message("⚠️ Movement module not loaded.", ephemeral=True)
            return

        await interaction.response.defer()
        summary = await movement_cog.gather_to_town_square(interaction.guild, interaction.user)
        if summary.error_message:
            await interaction.followup.send(f"⚠️ {summary.error_message}", ephemeral=True)
            return

        extra = (
            f" (cleaned up {summary.cleaned_cabins} temp cabin(s))"
            if summary.cleaned_cabins
            else ""
        )
        await interaction.followup.send(
            f"☀️ **Town Square Gathering:** Pulled **{summary.moved_count}** player(s) to {summary.target_description}{extra}.",
        )

    @discord.ui.button(
        label="Send to Cabins (Night)",
        emoji="🌙",
        style=discord.ButtonStyle.primary,
        custom_id="botc:panel:night",
        row=0,
    )
    async def btn_night(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        movement_cog = self.bot.get_cog("Movement")
        if movement_cog is None:
            await interaction.response.send_message("⚠️ Movement module not loaded.", ephemeral=True)
            return

        await interaction.response.defer()
        summary = await movement_cog.send_to_cabins(
            interaction.guild, invoker=interaction.user, include_invoker=True
        )
        if summary.error_message:
            await interaction.followup.send(f"⚠️ {summary.error_message}", ephemeral=True)
            return

        extra = (
            f" (created {summary.created_cabins} temp cabin(s))"
            if summary.created_cabins
            else ""
        )
        await interaction.followup.send(
            f"🌙 **Night Phase:** Sent **{summary.moved_count}** player(s) to **{summary.target_description}**{extra}.",
        )

    @discord.ui.button(
        label="Hush Square",
        emoji="🔇",
        style=discord.ButtonStyle.danger,
        custom_id="botc:panel:hush",
        row=0,
    )
    async def btn_hush(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        movement_cog = self.bot.get_cog("Movement")
        if movement_cog is None:
            await interaction.response.send_message("⚠️ Movement module not loaded.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        summary = await movement_cog.hush_town_square(interaction.guild, interaction.user)
        if summary.error_message:
            await interaction.followup.send(f"⚠️ {summary.error_message}", ephemeral=True)
            return

        await interaction.followup.send(
            f"🔇 **Storyteller Floor Active:** Muted **{summary.affected_count}** player(s) in {summary.target_description}. "
            f"Click **🔊 Unhush All** when ready to open the floor.",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Unhush All",
        emoji="🔊",
        style=discord.ButtonStyle.secondary,
        custom_id="botc:panel:unhush",
        row=0,
    )
    async def btn_unhush(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        movement_cog = self.bot.get_cog("Movement")
        if movement_cog is None:
            await interaction.response.send_message("⚠️ Movement module not loaded.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        summary = await movement_cog.unhush_all(interaction.guild, interaction.user)
        await interaction.followup.send(
            f"🔊 **Floor Open:** Unmuted **{summary.affected_count}** player(s).",
            ephemeral=True,
        )

    # -------------------------------------------------------------------------
    # Row 1: Quick Day Timers (1-minute fidelity + auto-gather)
    # -------------------------------------------------------------------------

    @discord.ui.button(
        label="8m Timer",
        emoji="⏱️",
        style=discord.ButtonStyle.secondary,
        custom_id="botc:panel:timer8",
        row=1,
    )
    async def btn_timer_8(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._start_quick_timer(interaction, minutes=8)

    @discord.ui.button(
        label="5m Timer",
        emoji="⏱️",
        style=discord.ButtonStyle.secondary,
        custom_id="botc:panel:timer5",
        row=1,
    )
    async def btn_timer_5(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._start_quick_timer(interaction, minutes=5)

    @discord.ui.button(
        label="3m Timer",
        emoji="⏱️",
        style=discord.ButtonStyle.secondary,
        custom_id="botc:panel:timer3",
        row=1,
    )
    async def btn_timer_3(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._start_quick_timer(interaction, minutes=3)

    @discord.ui.button(
        label="1m Timer",
        emoji="⏱️",
        style=discord.ButtonStyle.secondary,
        custom_id="botc:panel:timer1",
        row=1,
    )
    async def btn_timer_1(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._start_quick_timer(interaction, minutes=1)

    # -------------------------------------------------------------------------
    # Row 2: Timer Adjustments & Storyteller / Player Utilities
    # -------------------------------------------------------------------------

    @discord.ui.button(
        label="+1m",
        emoji="➕",
        style=discord.ButtonStyle.secondary,
        custom_id="botc:panel:timer_add1",
        row=2,
    )
    async def btn_timer_add(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not interaction.guild:
            return
        timer_cog = self.bot.get_cog("timer") or self.bot.get_cog("TimerCog")
        if timer_cog is None:
            await interaction.response.send_message("⚠️ Timer module not loaded.", ephemeral=True)
            return

        updated = await timer_cog.add_minutes(interaction.guild.id, 1)
        if not updated:
            await interaction.response.send_message(
                "⚠️ No timer is currently running. Click one of the timer buttons to start one!",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"➕ Added **1 minute** to the Day timer (**{updated.remaining_minutes}m** remaining).",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Stop Timer",
        emoji="🛑",
        style=discord.ButtonStyle.danger,
        custom_id="botc:panel:timer_stop",
        row=2,
    )
    async def btn_timer_stop(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not interaction.guild:
            return
        timer_cog = self.bot.get_cog("timer") or self.bot.get_cog("TimerCog")
        if timer_cog is None:
            await interaction.response.send_message("⚠️ Timer module not loaded.", ephemeral=True)
            return

        stopped = await timer_cog.cancel_timer(interaction.guild.id, notify=True)
        if not stopped:
            await interaction.response.send_message(
                "ℹ️ No active timer is running right now.", ephemeral=True
            )
            return

        await interaction.response.send_message("🛑 Stopped the Day timer.", ephemeral=True)

    @discord.ui.button(
        label="Visit Player Cabin",
        emoji="🧭",
        style=discord.ButtonStyle.secondary,
        custom_id="botc:panel:visit",
        row=2,
    )
    async def btn_visit(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        active_channels = config_manager.get_active_voice_channels(
            interaction.guild, interaction.user
        )
        options: list[discord.SelectOption] = []

        for vc in active_channels:
            for member in vc.members:
                if member.bot or member.id == interaction.user.id:
                    continue
                options.append(
                    discord.SelectOption(
                        label=member.display_name[:100],
                        value=str(member.id),
                        description=f"In {vc.name}"[:100],
                        emoji="🏠",
                    )
                )
                if len(options) >= 25:
                    break
            if len(options) >= 25:
                break

        if not options:
            await interaction.response.send_message(
                "ℹ️ No other players are currently in the BotC voice channels.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Select a player below to jump directly into their voice channel:",
            view=VisitPlayerView(options),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Player Help & Scripts",
        emoji="📚",
        style=discord.ButtonStyle.secondary,
        custom_id="botc:panel:help",
        row=2,
    )
    async def btn_help(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_message(
            embed=build_help_embed(), ephemeral=True
        )

    async def _start_quick_timer(
        self, interaction: discord.Interaction, minutes: int
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not interaction.channel:
            return

        timer_cog = self.bot.get_cog("timer") or self.bot.get_cog("TimerCog")
        if timer_cog is None:
            await interaction.response.send_message("⚠️ Timer module not loaded.", ephemeral=True)
            return

        target_ch = config_manager.resolve_alert_channel(
            interaction.guild, fallback_channel=interaction.channel
        )
        ch_mention = (
            target_ch.mention
            if isinstance(target_ch, discord.TextChannel)
            else "this channel"
        )

        await interaction.response.send_message(
            f"⏱️ Started a **{minutes}-minute** Day timer in {ch_mention} (auto-gather enabled).",
            ephemeral=True,
        )
        await timer_cog.start_timer(
            guild=interaction.guild,
            channel=interaction.channel,
            invoker=interaction.user,
            minutes=minutes,
            auto_gather=True,
        )


def build_panel_embed(guild: discord.Guild, invoker: discord.Member) -> discord.Embed:
    town_square = config_manager.resolve_town_square(guild, invoker)
    cabins_cat = config_manager.resolve_cabins_category(guild)
    alert_ch = config_manager.resolve_alert_channel(guild)

    ts_display = town_square.mention if town_square else "*Auto-detected when you join Town Square*"
    cabins_display = cabins_cat.name if cabins_cat else "*Auto-created on first Night phase*"
    alert_display = (
        alert_ch.mention
        if isinstance(alert_ch, discord.TextChannel)
        else "*Current channel (Set via `/setup configure alert_channel:#channel`)*"
    )

    embed = discord.Embed(
        title="🎛️ Storyteller Control Panel — Blood on the Clocktower",
        description=(
            "Use the buttons below to manage Day/Night transitions, hush Town Square for announcements, "
            "start countdown timers, or hop between sleeping players' cabins."
        ),
        color=discord.Color.dark_gold(),
    )
    embed.add_field(
        name="☀️ Day, 🌙 Night & 🔇 Storyteller Floor",
        value=(
            "• **Gather to Town Square:** Pulls everyone from Whispers & Cabins into Town Square and cleans up temporary cabins.\n"
            "• **Send to Cabins (Night):** Moves all players and the Storyteller to private Cabins (so night-order timing stays hidden).\n"
            "• **Hush Square / Unhush All:** Server-mutes non-Storytellers in Town Square for morning announcements or nominations."
        ),
        inline=False,
    )
    embed.add_field(
        name="⏱️ Day Timers (1-Minute Fidelity)",
        value=(
            "• Broadcasts in the **General Alert Channel**, updates every minute, posts a **1-minute warning**, "
            "and automatically gathers everyone to Town Square at `0:00`.\n"
            "• Need a custom duration? Use `/timer start <minutes>`."
        ),
        inline=False,
    )
    embed.add_field(
        name="📡 Detected Channels",
        value=(
            f"**Town Square:** {ts_display}\n"
            f"**General Alert Text Channel:** {alert_display}\n"
            f"**Cabins Category:** {cabins_display}"
        ),
        inline=False,
    )
    embed.set_footer(text="Tip: Anyone can click '📚 Player Help & Scripts' to view character sheets privately!")
    return embed


class PanelCog(commands.Cog, name="Panel"):
    """Provides the /panel command for an interactive Storyteller dashboard."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        # Register the persistent view so buttons continue working across bot restarts
        self.bot.add_view(StorytellerPanelView(self.bot))

    @app_commands.command(
        name="panel",
        description="🎛️ Post the interactive Storyteller Control Panel with Day/Night/Timer buttons.",
    )
    async def panel_command(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command must be used in a server.", ephemeral=True
            )
            return

        embed = build_panel_embed(interaction.guild, interaction.user)
        view = StorytellerPanelView(self.bot)
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PanelCog(bot))
