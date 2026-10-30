from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import config_manager

logger = logging.getLogger("clocktower_bot.movement")


@dataclass
class MovementSummary:
    moved_count: int
    skipped_count: int
    created_cabins: int
    cleaned_cabins: int
    target_description: str
    error_message: Optional[str] = None


@dataclass
class HushSummary:
    affected_count: int
    skipped_count: int
    target_description: str
    error_message: Optional[str] = None


class MovementCog(commands.Cog, name="Movement"):
    """Handles moving players between the Town Square, Whispers, and Night Cabins."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Limit concurrent Discord API writes to avoid burst 429 rate-limit warnings
        self._api_sem = asyncio.Semaphore(4)

    # -------------------------------------------------------------------------
    # Core Reusable Logic (called by both Slash Commands, Timer, and Panel)
    # -------------------------------------------------------------------------

    async def gather_to_town_square(
        self,
        guild: discord.Guild,
        invoker: Optional[discord.Member] = None,
    ) -> MovementSummary:
        """Moves everyone in BotC Day/Cabin voice channels into the Town Square and cleans up temp cabins."""
        if invoker is not None:
            config_manager.set_current_storyteller(guild.id, invoker.id)

        town_square = config_manager.resolve_town_square(guild, invoker)
        if town_square is None:
            return MovementSummary(
                moved_count=0,
                skipped_count=0,
                created_cabins=0,
                cleaned_cabins=0,
                target_description="Unknown",
                error_message=(
                    "Could not automatically locate a **Town Square** voice channel. "
                    "Either join the Town Square voice channel first, name a voice channel `Town Square`, "
                    "or configure one with `/setup configure`."
                ),
            )

        active_channels = config_manager.get_active_voice_channels(guild, invoker)
        members_to_move: list[discord.Member] = []
        already_in_square = 0

        for vc in active_channels:
            for member in vc.members:
                if member.bot:
                    continue
                if vc.id == town_square.id:
                    already_in_square += 1
                else:
                    members_to_move.append(member)

        # Move members concurrently in small batches to respect Discord rate limits
        move_tasks = [
            self._safe_move(member, town_square, reason="BotC: Gather to Town Square")
            for member in members_to_move
        ]
        results = await asyncio.gather(*move_tasks)
        moved_count = sum(1 for ok in results if ok)

        # Note: We KEEP temporary cabins intact during the game so we don't hit Discord's strict
        # channel-creation / permission-edit rate limits on every single Night transition!
        # (Use `/setup delete-auto` when your session is over to remove all cabins at once.)
        return MovementSummary(
            moved_count=moved_count,
            skipped_count=already_in_square,
            created_cabins=0,
            cleaned_cabins=0,
            target_description=town_square.mention,
        )

    async def send_to_cabins(
        self,
        guild: discord.Guild,
        invoker: Optional[discord.Member] = None,
        include_invoker: bool = True,
    ) -> MovementSummary:
        """Sends all active participants (including the Storyteller, excluding Spectators) to individual private Cabin voice channels."""
        if invoker is not None:
            config_manager.set_current_storyteller(guild.id, invoker.id)

        cabins_cat = await config_manager.ensure_cabins_category(guild)
        active_channels = config_manager.get_active_voice_channels(guild, invoker)

        # Identify participants to move (Storytellers also get their own cabin so night order stays hidden!)
        players_to_assign: list[discord.Member] = []
        skipped_count = 0

        # Track which existing cabins already have a single sleeping player in them
        occupied_cabin_ids: set[int] = set()
        existing_cabins = list(cabins_cat.voice_channels)

        for vc in active_channels:
            for member in vc.members:
                if member.bot:
                    continue

                is_spec = config_manager.is_spectator(member)
                if is_spec or (not include_invoker and invoker and member.id == invoker.id):
                    skipped_count += 1
                    continue

                # If player is already alone in a cabin inside the Cabins category, lock it privately for them and leave them there
                if vc.category_id == cabins_cat.id and len([m for m in vc.members if not m.bot]) == 1:
                    occupied_cabin_ids.add(vc.id)
                    await self._apply_private_cabin_permissions(guild, vc, member, invoker)
                    skipped_count += 1
                    continue

                players_to_assign.append(member)

        if not players_to_assign:
            return MovementSummary(
                moved_count=0,
                skipped_count=skipped_count,
                created_cabins=0,
                cleaned_cabins=0,
                target_description=cabins_cat.name,
                error_message=(
                    f"No movable players found in the active voice channels "
                    f"(Skipped **{skipped_count}** Spectator/already-in-cabin user(s))."
                ),
            )

        # Find empty existing cabins in the Cabins category
        pool_cabins: list[discord.VoiceChannel] = [
            vc
            for vc in existing_cabins
            if vc.id not in occupied_cabin_ids and len(vc.members) == 0
        ]

        # 1. Match players to their OWN previously-created cabin first (0 channel creations & 0 permission edits!)
        assigned_pairs: list[tuple[discord.Member, discord.VoiceChannel]] = []
        used_cabin_ids: set[int] = set()
        unmatched_players: list[discord.Member] = []

        for player in players_to_assign:
            expected_name = f"🔒 Cabin • {player.display_name[:20]}".lower()
            own_cabin = discord.utils.find(
                lambda vc, exp=expected_name: vc.id not in used_cabin_ids
                and (
                    vc.name.lower() == exp
                    or player in vc.overwrites
                ),
                pool_cabins,
            )
            if own_cabin is not None:
                assigned_pairs.append((player, own_cabin))
                used_cabin_ids.add(own_cabin.id)
            else:
                unmatched_players.append(player)

        remaining_cabins = [vc for vc in pool_cabins if vc.id not in used_cabin_ids]

        # 2. Pair any remaining unmatched players with generic empty cabins
        for player, cabin in zip(unmatched_players, remaining_cabins):
            assigned_pairs.append((player, cabin))
            used_cabin_ids.add(cabin.id)

        # 3. Only update permissions on cabins where the player or Storyteller doesn't already have access
        lock_tasks = [
            self._apply_private_cabin_permissions(guild, cabin, player, invoker)
            for player, cabin in assigned_pairs
        ]
        if lock_tasks:
            await asyncio.gather(*lock_tasks)

        # 4. If we still have players without a cabin, create new temporary cabins for them
        still_needing_cabins = unmatched_players[len(remaining_cabins) :]
        created_cabins = 0
        if still_needing_cabins:
            create_tasks = [
                self._create_temp_cabin(guild, cabins_cat, player, invoker)
                for player in still_needing_cabins
            ]
            newly_created = await asyncio.gather(*create_tasks)
            for player, vc in zip(still_needing_cabins, newly_created):
                if vc is not None:
                    assigned_pairs.append((player, vc))
                    created_cabins += 1

        if not assigned_pairs:
            return MovementSummary(
                moved_count=0,
                skipped_count=skipped_count,
                created_cabins=0,
                cleaned_cabins=0,
                target_description=cabins_cat.name,
                error_message=(
                    f"Found **{len(players_to_assign)}** player(s) to move, but failed to create Cabin voice channels in **{cabins_cat.name}**! "
                    "Please make sure the Bot's Role in **Server Settings -> Roles** has **Manage Channels**, **Manage Roles** (Manage Permissions), and **Move Members** enabled."
                ),
            )

        # Safety net: Ensure nobody is sent to their cabin still server-muted from a previous Hush
        await self.unhush_all(guild, invoker)

        # Move each player into their assigned cabin
        move_tasks = [
            self._safe_move(player, cabin, reason="BotC: Send to Night Cabin")
            for player, cabin in assigned_pairs
        ]

        results = await asyncio.gather(*move_tasks)
        moved_count = sum(1 for ok in results if ok)

        if moved_count == 0 and players_to_assign:
            return MovementSummary(
                moved_count=0,
                skipped_count=skipped_count,
                created_cabins=created_cabins,
                cleaned_cabins=0,
                target_description=cabins_cat.name,
                error_message=(
                    f"Created/found cabins for **{len(players_to_assign)}** player(s), but Discord blocked moving them! "
                    "Make sure the Bot's Role has **Move Members** and **Connect** permissions enabled."
                ),
            )

        return MovementSummary(
            moved_count=moved_count,
            skipped_count=skipped_count,
            created_cabins=created_cabins,
            cleaned_cabins=0,
            target_description=cabins_cat.name,
        )

    async def cleanup_temp_cabins(self, guild: discord.Guild) -> int:
        """Deletes empty temporary cabin channels created by the bot (by saved ID or name match)."""
        cfg = config_manager.get(guild.id)
        tracked_ids = set(cfg.temp_cabin_ids)

        candidates: dict[int, discord.VoiceChannel] = {}
        for channel_id in list(tracked_ids):
            ch = guild.get_channel(channel_id)
            if ch is None:
                config_manager.unregister_temp_cabin(guild.id, channel_id)
            elif isinstance(ch, discord.VoiceChannel):
                candidates[ch.id] = ch

        # Also match any auto-generated temporary cabins by name prefix (survives bot restarts!)
        cabins_cat = config_manager.resolve_cabins_category(guild)
        search_channels = list(cabins_cat.voice_channels) if cabins_cat else list(guild.voice_channels)
        for vc in search_channels:
            lower = vc.name.lower()
            if vc.name.startswith("🔒 Cabin •") or lower.startswith("cabin •"):
                candidates[vc.id] = vc

        cleaned = 0
        for cid, vc in candidates.items():
            if len(vc.members) == 0:
                try:
                    await vc.delete(reason="BotC: Cleaning up temporary Night Cabin")
                    config_manager.unregister_temp_cabin(guild.id, cid)
                    cleaned += 1
                except discord.HTTPException:
                    pass
        return cleaned

    def _build_cabin_overwrites(
        self,
        guild: discord.Guild,
        player: discord.Member,
        invoker: Optional[discord.Member] = None,
    ) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
        """Builds permission overwrites so ONLY the assigned player, Storyteller(s), and Bot can see the cabin.

        Note: Only sets permissions the bot is guaranteed to hold (view_channel, connect, speak)
        so Discord never rejects the overwrite with 403 Missing Permissions!
        """
        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False,
                connect=False,
            ),
            player: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
            ),
        }

        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
            )

        if invoker:
            overwrites[invoker] = discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
            )

        # Also ensure the remembered current_storyteller_id has access
        cfg = config_manager.get(guild.id)
        if cfg.current_storyteller_id:
            st_member = guild.get_member(cfg.current_storyteller_id)
            if st_member and st_member not in overwrites:
                overwrites[st_member] = discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    speak=True,
                )

        # Also grant view/connect to any co-storytellers with [ST] in their nickname currently in voice
        for vc in guild.voice_channels:
            for member in vc.members:
                if not member.bot and config_manager.is_storyteller(member, invoker):
                    overwrites[member] = discord.PermissionOverwrite(
                        view_channel=True,
                        connect=True,
                        speak=True,
                    )

        return overwrites

    async def _apply_private_cabin_permissions(
        self,
        guild: discord.Guild,
        cabin: discord.VoiceChannel,
        player: discord.Member,
        invoker: Optional[discord.Member] = None,
    ) -> None:
        """Updates an existing cabin's overwrites ONLY if they don't already match (avoids Discord's 2-edits/10m rate limit)."""
        desired = self._build_cabin_overwrites(guild, player, invoker)

        # Fast-path check: If @everyone is already denied view_channel and both the player & Storyteller
        # already have view_channel=True on this cabin, skip the expensive channel.edit() API call!
        current = cabin.overwrites
        everyone_ow = current.get(guild.default_role)
        player_ow = current.get(player)
        invoker_ok = (invoker is None) or (
            invoker in current and current[invoker].view_channel is True
        )
        other_members_in_ow = [
            k for k in current.keys()
            if isinstance(k, discord.Member) and k not in desired
        ]

        if (
            everyone_ow is not None
            and everyone_ow.view_channel is False
            and player_ow is not None
            and player_ow.view_channel is True
            and invoker_ok
            and not other_members_in_ow
        ):
            return

        try:
            async with self._api_sem:
                await cabin.edit(
                    overwrites=desired,
                    reason=f"BotC: Locking private Night Cabin for {player.display_name}",
                )
        except discord.HTTPException as exc:
            logger.warning(
                "Could not set private overwrites on existing cabin %s: %s (Ensure bot role has 'Manage Roles' permission)",
                cabin.name,
                exc,
            )

    async def _create_temp_cabin(
        self,
        guild: discord.Guild,
        category: discord.CategoryChannel,
        player: discord.Member,
        invoker: Optional[discord.Member] = None,
    ) -> Optional[discord.VoiceChannel]:
        """Creates a private temporary cabin channel visible only to the player and Storyteller."""
        safe_name = player.display_name[:20]
        overwrites = self._build_cabin_overwrites(guild, player, invoker)
        try:
            async with self._api_sem:
                vc = await guild.create_voice_channel(
                    name=f"🔒 Cabin • {safe_name}",
                    category=category,
                    overwrites=overwrites,
                    user_limit=2,  # Player + visiting Storyteller
                    reason=f"BotC: Temporary Night Cabin for {player.display_name}",
                )
            config_manager.register_temp_cabin(guild.id, vc.id)
            return vc
        except discord.HTTPException as exc:
            logger.warning(
                "Discord rejected private overwrites when creating cabin for %s: %s. "
                "Falling back to standard channel + per-target set_permissions...",
                player.display_name,
                exc,
            )
            try:
                async with self._api_sem:
                    vc = await guild.create_voice_channel(
                        name=f"🔒 Cabin • {safe_name}",
                        category=category,
                        user_limit=2,
                        reason=f"BotC: Temporary Night Cabin for {player.display_name} (fallback)",
                    )
                config_manager.register_temp_cabin(guild.id, vc.id)
                # Try applying each overwrite individually via set_permissions
                for target, overwrite in overwrites.items():
                    try:
                        async with self._api_sem:
                            await vc.set_permissions(target, overwrite=overwrite)
                    except discord.HTTPException as perm_exc:
                        logger.warning(
                            "set_permissions failed for %s on %s: %s",
                            target,
                            vc.name,
                            perm_exc,
                        )
                return vc
            except discord.HTTPException as fallback_exc:
                logger.error("Failed to create cabin channel completely: %s", fallback_exc)
                return None

    async def _safe_move(
        self,
        member: discord.Member,
        target: discord.VoiceChannel,
        reason: str,
    ) -> bool:
        try:
            async with self._api_sem:
                await member.move_to(target, reason=reason)
            return True
        except discord.HTTPException:
            return False

    async def _safe_mute(
        self,
        member: discord.Member,
        mute: bool,
        reason: str,
    ) -> bool:
        try:
            async with self._api_sem:
                await member.edit(mute=mute, reason=reason)
            return True
        except discord.HTTPException:
            return False

    async def hush_town_square(
        self,
        guild: discord.Guild,
        invoker: Optional[discord.Member] = None,
    ) -> HushSummary:
        """Server-mutes all non-Storyteller players in the Town Square so the Storyteller has the floor."""
        if invoker is not None:
            config_manager.set_current_storyteller(guild.id, invoker.id)

        town_square = config_manager.resolve_town_square(guild, invoker)
        if town_square is None:
            return HushSummary(
                affected_count=0,
                skipped_count=0,
                target_description="Unknown",
                error_message=(
                    "Could not locate a **Town Square** voice channel. "
                    "Join the Town Square voice channel first or set it via `/setup configure`."
                ),
            )

        to_mute: list[discord.Member] = []
        skipped = 0
        for member in town_square.members:
            if member.bot or config_manager.is_storyteller(member, invoker):
                skipped += 1
                continue
            if member.voice and not member.voice.mute:
                to_mute.append(member)
            else:
                skipped += 1

        tasks = [
            self._safe_mute(m, True, reason="BotC: Storyteller Floor (Hush Town Square)")
            for m in to_mute
        ]
        results = await asyncio.gather(*tasks)
        muted_ids = [m.id for m, ok in zip(to_mute, results) if ok]
        config_manager.register_hushed_members(guild.id, muted_ids)

        return HushSummary(
            affected_count=len(muted_ids),
            skipped_count=skipped,
            target_description=town_square.mention,
        )

    async def unhush_all(
        self,
        guild: discord.Guild,
        invoker: Optional[discord.Member] = None,
    ) -> HushSummary:
        """Unmutes all server-muted players across active BotC voice channels (and any tracked hushed members)."""
        tracked_ids = set(config_manager.clear_hushed_members(guild.id))
        active_channels = config_manager.get_active_voice_channels(guild, invoker)

        to_unmute: dict[int, discord.Member] = {}
        for vc in active_channels:
            for member in vc.members:
                if member.bot:
                    continue
                if (member.voice and member.voice.mute) or member.id in tracked_ids:
                    to_unmute[member.id] = member

        for mid in tracked_ids:
            if mid not in to_unmute:
                m = guild.get_member(mid)
                if m and m.voice and m.voice.mute:
                    to_unmute[mid] = m

        members_list = list(to_unmute.values())
        tasks = [
            self._safe_mute(m, False, reason="BotC: Unhush Town Square")
            for m in members_list
        ]
        results = await asyncio.gather(*tasks)
        unmuted_count = sum(1 for ok in results if ok)

        return HushSummary(
            affected_count=unmuted_count,
            skipped_count=0,
            target_description="BotC voice channels",
        )

    # -------------------------------------------------------------------------
    # Slash Commands
    # -------------------------------------------------------------------------

    @app_commands.command(
        name="square",
        description="☀️ Gather all players from Whispers and Cabins back to the Town Square.",
    )
    async def square_command(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        await interaction.response.defer()
        summary = await self.gather_to_town_square(interaction.guild, interaction.user)

        if summary.error_message:
            await interaction.followup.send(f"⚠️ {summary.error_message}", ephemeral=True)
            return

        extra = (
            f" (cleaned up {summary.cleaned_cabins} temporary cabin(s))"
            if summary.cleaned_cabins
            else ""
        )
        embed = discord.Embed(
            title="☀️ Town Square Gathering",
            description=(
                f"Moved **{summary.moved_count}** player(s) to {summary.target_description}{extra}.\n"
                f"*(Already in Town Square: {summary.skipped_count})*"
            ),
            color=discord.Color.gold(),
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="night",
        description="🌙 Send all active players (and the Storyteller) to private Night Cabins.",
    )
    @app_commands.describe(
        include_me="Also move yourself (the Storyteller) into a cabin (default: True)"
    )
    async def night_command(
        self,
        interaction: discord.Interaction,
        include_me: bool = True,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        await interaction.response.defer()
        summary = await self.send_to_cabins(
            interaction.guild,
            invoker=interaction.user,
            include_invoker=include_me,
        )

        if summary.error_message:
            await interaction.followup.send(f"⚠️ {summary.error_message}", ephemeral=True)
            return

        extra = (
            f"\n✨ Created **{summary.created_cabins}** temporary cabin(s) on the fly."
            if summary.created_cabins
            else ""
        )
        embed = discord.Embed(
            title="🌙 Night Falls on Ravenswood Bluff",
            description=(
                f"Sent **{summary.moved_count}** player(s) to **{summary.target_description}**{extra}\n"
                f"*(Storytellers / already in cabins skipped: {summary.skipped_count})*"
            ),
            color=discord.Color.dark_purple(),
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="visit",
        description="🧭 Storyteller utility: Jump directly into the voice channel a player is in.",
    )
    @app_commands.describe(player="The player whose cabin/channel you want to visit")
    async def visit_command(
        self,
        interaction: discord.Interaction,
        player: discord.Member,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "⚠️ You must be connected to a voice channel first before I can move you!",
                ephemeral=True,
            )
            return

        if not player.voice or not isinstance(player.voice.channel, discord.VoiceChannel):
            await interaction.response.send_message(
                f"⚠️ **{player.display_name}** is not currently in a voice channel.",
                ephemeral=True,
            )
            return

        target_vc = player.voice.channel
        try:
            await interaction.user.move_to(
                target_vc, reason=f"BotC: Storyteller visiting {player.display_name}"
            )
            await interaction.response.send_message(
                f"🧭 Moved you to **{target_vc.name}** with **{player.display_name}**.",
                ephemeral=True,
            )
        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"⚠️ Could not move you to {target_vc.mention}: {exc}",
                ephemeral=True,
            )

    @app_commands.command(
        name="hush",
        description="🔇 Storyteller Floor: Server-mute players in Town Square (Storytellers stay unmuted).",
    )
    async def hush_command(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        summary = await self.hush_town_square(interaction.guild, interaction.user)
        if summary.error_message:
            await interaction.followup.send(f"⚠️ {summary.error_message}", ephemeral=True)
            return

        await interaction.followup.send(
            f"🔇 **Storyteller Floor Active:** Muted **{summary.affected_count}** player(s) in {summary.target_description}. "
            f"Run `/unhush` (or click **🔊 Unhush All** on `/panel`) when ready to open the floor.",
            ephemeral=True,
        )

    @app_commands.command(
        name="unhush",
        description="🔊 Unmute all hushed players across the BotC voice channels.",
    )
    async def unhush_command(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        summary = await self.unhush_all(interaction.guild, interaction.user)
        await interaction.followup.send(
            f"🔊 **Floor Open:** Unmuted **{summary.affected_count}** player(s).",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MovementCog(bot))
