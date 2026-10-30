from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import config_manager


@dataclass
class ActiveTimer:
    guild_id: int
    channel: discord.abc.Messageable
    invoker: discord.Member
    remaining_minutes: int
    total_minutes: int
    auto_gather: bool
    task: Optional[asyncio.Task] = None
    status_message: Optional[discord.Message] = None
    warning_message: Optional[discord.Message] = None


class TimerCog(
    commands.GroupCog,
    name="timer",
    group_name="timer",
    group_description="⏱️ Day phase timers (1-minute fidelity) with optional auto-gather to Town Square.",
):
    """Manages 1-minute fidelity Day timers for Blood on the Clocktower."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.active_timers: dict[int, ActiveTimer] = {}

    def cog_unload(self) -> None:
        for timer in self.active_timers.values():
            if timer.task and not timer.task.done():
                timer.task.cancel()
        self.active_timers.clear()

    def get_timer(self, guild_id: int) -> Optional[ActiveTimer]:
        return self.active_timers.get(guild_id)

    # -------------------------------------------------------------------------
    # Core Reusable Timer Methods (used by Slash Commands and Panel)
    # -------------------------------------------------------------------------

    async def start_timer(
        self,
        guild: discord.Guild,
        channel: discord.abc.Messageable,
        invoker: discord.Member,
        minutes: int,
        auto_gather: bool = True,
    ) -> ActiveTimer:
        """Starts (or replaces) a 1-minute fidelity countdown timer for the guild."""
        config_manager.set_current_storyteller(guild.id, invoker.id)
        await self.cancel_timer(guild.id, notify=False)

        # Safety net: If players were hushed in Town Square for morning announcements, unmute them when the Day timer starts
        movement_cog = self.bot.get_cog("Movement")
        if movement_cog is not None:
            await movement_cog.unhush_all(guild, invoker)

        target_channel = config_manager.resolve_alert_channel(guild, fallback_channel=channel) or channel

        timer = ActiveTimer(
            guild_id=guild.id,
            channel=target_channel,
            invoker=invoker,
            remaining_minutes=minutes,
            total_minutes=minutes,
            auto_gather=auto_gather,
        )
        self.active_timers[guild.id] = timer

        embed = self._build_timer_embed(timer)
        try:
            timer.status_message = await target_channel.send(embed=embed)
        except discord.HTTPException:
            timer.status_message = None

        timer.task = asyncio.create_task(self._run_timer_loop(guild, timer))
        return timer

    async def add_minutes(self, guild_id: int, extra_minutes: int) -> Optional[ActiveTimer]:
        """Adds (or subtracts) minutes from an active timer and refreshes its status embed."""
        timer = self.active_timers.get(guild_id)
        if not timer:
            return None

        timer.remaining_minutes = max(1, timer.remaining_minutes + extra_minutes)
        timer.total_minutes = max(timer.total_minutes, timer.remaining_minutes)

        if timer.status_message:
            try:
                await timer.status_message.edit(embed=self._build_timer_embed(timer))
            except discord.HTTPException:
                pass
        return timer

    async def cancel_timer(self, guild_id: int, notify: bool = True) -> bool:
        """Cancels an active timer for the guild if one is running and cleans up its messages."""
        timer = self.active_timers.pop(guild_id, None)
        if not timer:
            return False

        if timer.task and not timer.task.done():
            timer.task.cancel()

        if timer.warning_message:
            try:
                await timer.warning_message.delete()
            except discord.HTTPException:
                pass

        if timer.status_message:
            try:
                await timer.status_message.delete()
            except discord.HTTPException:
                pass

        if notify:
            stopped_embed = discord.Embed(
                title="🛑 Timer Cancelled",
                description="The Day timer was stopped early by the Storyteller.",
                color=discord.Color.red(),
            )
            try:
                await timer.channel.send(embed=stopped_embed, delete_after=15.0)
            except discord.HTTPException:
                pass

        return True

    async def _run_timer_loop(self, guild: discord.Guild, timer: ActiveTimer) -> None:
        try:
            while timer.remaining_minutes > 0:
                await asyncio.sleep(60)
                timer.remaining_minutes -= 1

                if timer.remaining_minutes > 0:
                    # Update existing timer message every minute
                    if timer.status_message:
                        try:
                            await timer.status_message.edit(
                                embed=self._build_timer_embed(timer)
                            )
                        except discord.HTTPException:
                            pass

                    # Send an explicit 1-minute warning notice in text chat
                    if timer.remaining_minutes == 1:
                        try:
                            timer.warning_message = await timer.channel.send(
                                "⚠️ **1 minute remaining** in private whispers! Wrap up your conversations."
                            )
                        except discord.HTTPException:
                            pass

            # Timer reached 0:00
            self.active_timers.pop(guild.id, None)
            await self._on_timer_expired(guild, timer)

        except asyncio.CancelledError:
            return

    async def _on_timer_expired(self, guild: discord.Guild, timer: ActiveTimer) -> None:
        # Delete the countdown embed and 1-minute warning message so chat stays clean
        if timer.warning_message:
            try:
                await timer.warning_message.delete()
            except discord.HTTPException:
                pass

        if timer.status_message:
            try:
                await timer.status_message.delete()
            except discord.HTTPException:
                pass

        done_embed = discord.Embed(
            title="🔔 Time is Up!",
            description="The Day timer has finished.",
            color=discord.Color.gold(),
        )

        if timer.auto_gather:
            movement_cog = self.bot.get_cog("Movement")
            if movement_cog is not None:
                summary = await movement_cog.gather_to_town_square(guild, timer.invoker)
                if summary.error_message:
                    done_embed.add_field(
                        name="Auto-Gather Notice",
                        value=f"⚠️ {summary.error_message}",
                        inline=False,
                    )
                else:
                    done_embed.add_field(
                        name="☀️ Auto-Gathered to Town Square",
                        value=f"Pulled **{summary.moved_count}** player(s) to {summary.target_description}.",
                        inline=False,
                    )

        try:
            # Post the Time is Up! notice and auto-delete it after 30 seconds
            await timer.channel.send(embed=done_embed, delete_after=30.0)
        except discord.HTTPException:
            pass

    @staticmethod
    def _build_timer_embed(timer: ActiveTimer) -> discord.Embed:
        end_dt = datetime.now(timezone.utc) + timedelta(minutes=timer.remaining_minutes)
        discord_ts = discord.utils.format_dt(end_dt, style="R")
        exact_ts = discord.utils.format_dt(end_dt, style="t")

        filled_blocks = max(0, min(10, round((timer.remaining_minutes / max(1, timer.total_minutes)) * 10)))
        bar = "🟨" * filled_blocks + "⬛" * (10 - filled_blocks)

        auto_text = "☀️ Auto-gather to Town Square at 0:00" if timer.auto_gather else "🔔 Alert only at 0:00 (no auto-move)"

        embed = discord.Embed(
            title="⏳ Day Phase Timer Running",
            description=(
                f"**{timer.remaining_minutes} minute(s)** remaining ({discord_ts} at {exact_ts})\n"
                f"{bar}\n\n"
                f"*{auto_text}*"
            ),
            color=discord.Color.orange() if timer.remaining_minutes > 1 else discord.Color.red(),
        )
        embed.set_footer(text=f"Started by {timer.invoker.display_name} • 1-minute fidelity updates")
        return embed

    # -------------------------------------------------------------------------
    # Slash Commands (/timer start, /timer add, /timer cancel)
    # -------------------------------------------------------------------------

    @app_commands.command(
        name="start",
        description="⏱️ Start a countdown timer (1-minute fidelity) with optional auto-gather to Town Square.",
    )
    @app_commands.describe(
        minutes="Duration in minutes (1 to 60)",
        auto_gather="Automatically pull everyone to Town Square when time expires (default: True)",
    )
    async def timer_start(
        self,
        interaction: discord.Interaction,
        minutes: app_commands.Range[int, 1, 60],
        auto_gather: bool = True,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not interaction.channel:
            await interaction.response.send_message(
                "This command must be run inside a server text channel.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"⏱️ Started a **{minutes}-minute** timer (Auto-gather: **{'On' if auto_gather else 'Off'}**).",
            ephemeral=True,
        )
        await self.start_timer(
            guild=interaction.guild,
            channel=interaction.channel,
            invoker=interaction.user,
            minutes=minutes,
            auto_gather=auto_gather,
        )

    @app_commands.command(
        name="add",
        description="➕ Add extra minutes to the currently running Day timer.",
    )
    @app_commands.describe(minutes="Minutes to add (e.g., 1, 2, 5)")
    async def timer_add(
        self,
        interaction: discord.Interaction,
        minutes: app_commands.Range[int, 1, 30] = 1,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command must be run inside a server.", ephemeral=True
            )
            return

        timer = await self.add_minutes(interaction.guild.id, minutes)
        if not timer:
            await interaction.response.send_message(
                "⚠️ There is no active timer running right now. Use `/timer start` first.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"➕ Added **{minutes} minute(s)**. Remaining time: **{timer.remaining_minutes} minute(s)**.",
            ephemeral=False,
        )

    @app_commands.command(
        name="cancel",
        description="🛑 Stop the currently running Day timer.",
    )
    async def timer_cancel(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command must be run inside a server.", ephemeral=True
            )
            return

        stopped = await self.cancel_timer(interaction.guild.id, notify=True)
        if not stopped:
            await interaction.response.send_message(
                "⚠️ There is no active timer running right now.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "🛑 Stopped the active Day timer.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TimerCog(bot))
