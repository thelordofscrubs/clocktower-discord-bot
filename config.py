from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import discord

CONFIG_PATH = Path(__file__).parent / "data" / "guild_config.json"

TOWN_SQUARE_KEYWORDS = ("town square", "town-square", "townsquare", "square", "town center", "day")
CABIN_CATEGORY_KEYWORDS = ("cabin", "cabins", "night", "sleep", "cottages", "bedrooms")
STORYTELLER_KEYWORDS = ("storyteller", "story teller", "[st]", "(st)")
SPECTATOR_KEYWORDS = ("spectator", "[spec]", "(spec)")


@dataclass
class GuildConfig:
    guild_id: int
    town_square_id: Optional[int] = None
    day_category_id: Optional[int] = None
    cabins_category_id: Optional[int] = None
    storyteller_role_id: Optional[int] = None
    current_storyteller_id: Optional[int] = None
    alert_channel_id: Optional[int] = None
    temp_cabin_ids: list[int] = field(default_factory=list)
    hushed_member_ids: list[int] = field(default_factory=list)


class ConfigManager:
    """Manages per-guild configuration and provides smart zero-config channel discovery."""

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path
        self._configs: dict[int, GuildConfig] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._configs = {}
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            valid_fields = set(GuildConfig.__dataclass_fields__.keys())
            self._configs = {
                int(gid): GuildConfig(
                    **{k: v for k, v in data.items() if k in valid_fields}
                )
                for gid, data in raw.items()
            }
        except (json.JSONDecodeError, TypeError, ValueError):
            self._configs = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {str(gid): asdict(cfg) for gid, cfg in self._configs.items()}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get(self, guild_id: int) -> GuildConfig:
        if guild_id not in self._configs:
            self._configs[guild_id] = GuildConfig(guild_id=guild_id)
            self.save()
        return self._configs[guild_id]

    def update(self, guild_id: int, **kwargs) -> GuildConfig:
        cfg = self.get(guild_id)
        for key, value in kwargs.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        self.save()
        return cfg

    def register_temp_cabin(self, guild_id: int, channel_id: int) -> None:
        cfg = self.get(guild_id)
        if channel_id not in cfg.temp_cabin_ids:
            cfg.temp_cabin_ids.append(channel_id)
            self.save()

    def unregister_temp_cabin(self, guild_id: int, channel_id: int) -> None:
        cfg = self.get(guild_id)
        if channel_id in cfg.temp_cabin_ids:
            cfg.temp_cabin_ids.remove(channel_id)
            self.save()

    def register_hushed_members(self, guild_id: int, member_ids: list[int]) -> None:
        cfg = self.get(guild_id)
        changed = False
        for mid in member_ids:
            if mid not in cfg.hushed_member_ids:
                cfg.hushed_member_ids.append(mid)
                changed = True
        if changed:
            self.save()

    def clear_hushed_members(self, guild_id: int) -> list[int]:
        cfg = self.get(guild_id)
        prev = list(cfg.hushed_member_ids)
        if prev:
            cfg.hushed_member_ids.clear()
            self.save()
        return prev

    def set_current_storyteller(self, guild_id: int, member_id: int) -> None:
        cfg = self.get(guild_id)
        if cfg.current_storyteller_id != member_id:
            cfg.current_storyteller_id = member_id
            self.save()

    # -------------------------------------------------------------------------
    # Smart Zero-Config Discovery Helpers
    # -------------------------------------------------------------------------

    def resolve_town_square(
        self,
        guild: discord.Guild,
        invoker: Optional[discord.Member] = None,
    ) -> Optional[discord.VoiceChannel]:
        """Finds the Town Square voice channel via saved config, name match, or invoker's voice channel."""
        cfg = self.get(guild.id)

        # 1. Explicit configuration
        if cfg.town_square_id:
            ch = guild.get_channel(cfg.town_square_id)
            if isinstance(ch, discord.VoiceChannel):
                return ch

        # 2. Search by common Town Square names (prioritizing "town square" over broader matches)
        for keyword in TOWN_SQUARE_KEYWORDS:
            for vc in guild.voice_channels:
                if keyword in vc.name.lower():
                    return vc

        # 3. Fallback: If the Storyteller is currently in a voice channel (not a cabin), use that
        if invoker and invoker.voice and isinstance(invoker.voice.channel, discord.VoiceChannel):
            vc = invoker.voice.channel
            if vc.id not in cfg.temp_cabin_ids and "cabin" not in vc.name.lower():
                return vc

        return None

    def resolve_day_category(
        self,
        guild: discord.Guild,
        town_square: Optional[discord.VoiceChannel] = None,
    ) -> Optional[discord.CategoryChannel]:
        """Finds the Day Category via saved config or Town Square's parent category."""
        cfg = self.get(guild.id)
        if cfg.day_category_id:
            cat = guild.get_channel(cfg.day_category_id)
            if isinstance(cat, discord.CategoryChannel):
                return cat

        if town_square is None:
            town_square = self.resolve_town_square(guild)

        if town_square and town_square.category:
            return town_square.category

        # Fallback: Look for a category mentioning clocktower or botc or day
        for cat in guild.categories:
            lower = cat.name.lower()
            if any(k in lower for k in ("clocktower", "botc", "ravenswood", "day")):
                return cat

        return None

    def resolve_cabins_category(
        self,
        guild: discord.Guild,
    ) -> Optional[discord.CategoryChannel]:
        """Finds the Cabins / Night Category via saved config or name matching."""
        cfg = self.get(guild.id)
        if cfg.cabins_category_id:
            cat = guild.get_channel(cfg.cabins_category_id)
            if isinstance(cat, discord.CategoryChannel):
                return cat

        for cat in guild.categories:
            lower = cat.name.lower()
            if any(k in lower for k in CABIN_CATEGORY_KEYWORDS):
                return cat

        return None

    async def ensure_cabins_category(
        self,
        guild: discord.Guild,
    ) -> discord.CategoryChannel:
        """Returns the Cabins category, creating it automatically if none exists."""
        cat = self.resolve_cabins_category(guild)
        if cat is not None:
            return cat

        cat = await guild.create_category(
            name="🌙 BOTC - Cabins",
            reason="Blood on the Clocktower: Auto-created Night Cabins category",
        )
        self.update(guild.id, cabins_category_id=cat.id)
        return cat

    def is_storyteller(
        self,
        member: discord.Member,
        invoker: Optional[discord.Member] = None,
    ) -> bool:
        """Determines if a member is the current Storyteller (person who clicked the button/command or has [ST] in nickname)."""
        if member.bot:
            return True
        if invoker and member.id == invoker.id:
            return True

        cfg = self.get(member.guild.id)
        if cfg.current_storyteller_id and member.id == cfg.current_storyteller_id:
            return True

        # Also support explicit [ST] or (ST) tag in their server display name (e.g. for Co-Storytellers)
        display_lower = member.display_name.lower()
        if any(tag in display_lower for tag in STORYTELLER_KEYWORDS):
            return True

        return False

    def is_spectator(self, member: discord.Member) -> bool:
        """Determines if a member is marked as a Spectator via role or nickname tag."""
        display_lower = member.display_name.lower()
        if any(tag in display_lower for tag in SPECTATOR_KEYWORDS):
            return True
        for role in member.roles:
            if any(tag in role.name.lower() for tag in SPECTATOR_KEYWORDS):
                return True
        return False

    def get_active_voice_channels(
        self,
        guild: discord.Guild,
        invoker: Optional[discord.Member] = None,
    ) -> list[discord.VoiceChannel]:
        """Returns all voice channels belonging to the BotC Day and Cabins categories (plus invoker's channel)."""
        town_square = self.resolve_town_square(guild, invoker)
        day_cat = self.resolve_day_category(guild, town_square)
        cabins_cat = self.resolve_cabins_category(guild)

        channels: list[discord.VoiceChannel] = []
        seen_ids: set[int] = set()

        for cat in (day_cat, cabins_cat):
            if cat:
                for vc in cat.voice_channels:
                    if vc.id not in seen_ids:
                        channels.append(vc)
                        seen_ids.add(vc.id)

        if town_square and town_square.id not in seen_ids:
            channels.append(town_square)
            seen_ids.add(town_square.id)

        # Also include the voice channel the Storyteller is currently in (and its category)
        # in case the server has both a manual Town Square and an auto-created one!
        if invoker and invoker.voice and isinstance(invoker.voice.channel, discord.VoiceChannel):
            inv_vc = invoker.voice.channel
            if inv_vc.id not in seen_ids:
                channels.append(inv_vc)
                seen_ids.add(inv_vc.id)
            if inv_vc.category:
                for vc in inv_vc.category.voice_channels:
                    if vc.id not in seen_ids:
                        channels.append(vc)
                        seen_ids.add(vc.id)

        # If no category exists at all on the server, fallback to all guild voice channels (excluding AFK)
        if not channels:
            for vc in guild.voice_channels:
                if guild.afk_channel and vc.id == guild.afk_channel.id:
                    continue
                channels.append(vc)

        return channels

    def resolve_alert_channel(
        self,
        guild: discord.Guild,
        fallback_channel: Optional[discord.abc.Messageable] = None,
    ) -> Optional[discord.abc.Messageable]:
        """Resolves the public text channel for timer alerts and game announcements."""
        cfg = self.get(guild.id)
        if cfg.alert_channel_id:
            ch = guild.get_channel(cfg.alert_channel_id)
            if isinstance(ch, discord.TextChannel):
                return ch

        # Auto-discover a public text channel in the Day Category (skipping storyteller-only channels)
        day_cat = self.resolve_day_category(guild)
        if day_cat and day_cat.text_channels:
            for tc in day_cat.text_channels:
                lower = tc.name.lower()
                if any(st_word in lower for st_word in ("storyteller", "st-only", "st-chat", "mod", "admin")):
                    continue
                if any(k in lower for k in ("town", "square", "botc", "clocktower", "general", "chat", "game")):
                    return tc
            for tc in day_cat.text_channels:
                lower = tc.name.lower()
                if not any(st_word in lower for st_word in ("storyteller", "st-only", "st-chat", "mod", "admin")):
                    return tc

        return fallback_channel


config_manager = ConfigManager()
