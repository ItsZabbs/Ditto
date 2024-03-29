from __future__ import annotations

import datetime
import zoneinfo
from os import stat

import discord
from donphan import MaybeAcquire

from ..core.bot import BotBase
from ..db.tables import TimeZones
from ..utils.time import ALL_TIMEZONES
from .converters import DatetimeConverter

__all__ = (
    "GuildTransformer",
    "WhenAndWhatTransformer",
    "ZoneInfoTransformer",
)


class GuildTransformer(discord.app_commands.Transformer):
    @classmethod
    def type(cls) -> discord.AppCommandOptionType:
        return discord.AppCommandOptionType.integer

    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: int) -> discord.Guild:
        guild = interaction.client.get_guild(value)

        if guild is None:
            raise ValueError(f"Could not find guild with id '{value}'.")

        return guild

    @staticmethod
    async def autocomplete(_, interaction: discord.Interaction, value: str) -> list[discord.app_commands.Choice[int]]:
        suggestions = []

        for guild in interaction.client.guilds:
            if guild.get_member(interaction.user.id) is not None:
                suggestions.append(discord.app_commands.Choice(name=guild.name, value=guild.id))

        return suggestions[:25]


class WhenAndWhatTransformer(discord.app_commands.Transformer):
    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str) -> tuple[datetime.datetime, str]:
        assert isinstance(interaction.client, BotBase)

        async with MaybeAcquire(pool=interaction.client.pool) as connection:
            timezone = await TimeZones.get_timezone(connection, interaction.user) or datetime.timezone.utc

        now = interaction.created_at.astimezone(tz=timezone)

        # Strip some common stuff
        for prefix in ("me to ", "me in ", "me at ", "me that "):
            if value.startswith(prefix):
                argument = value[len(prefix) :]
                break

        for suffix in ("from now",):
            if value.endswith(suffix):
                argument = value[: -len(suffix)]

        argument = value.strip()

        # Determine the date argument
        parsed_times = await DatetimeConverter.parse(argument, timezone=timezone, now=now)

        if len(parsed_times) == 0:
            raise ValueError("Could not parse time.")
        elif len(parsed_times) > 1:
            ...  # TODO: Raise on too many?

        when, begin, end = parsed_times[0]

        if begin != 0 and end != len(argument):
            raise ValueError("Could not distinguish time from argument.")

        if begin == 0:
            what = argument[end + 1 :].lstrip(" ,.!:;")
        else:
            what = argument[:begin].strip()

        for prefix in ("to ",):
            if what.startswith(prefix):
                what = what[len(prefix) :]

        return (when, what)


class ZoneInfoTransformer(discord.app_commands.Transformer):
    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str) -> zoneinfo.ZoneInfo:
        try:
            return zoneinfo.ZoneInfo(value)
        except Exception:  # catch all due to BPO: 41530
            raise ValueError(f'Time Zone "{value}" not found.')

    @classmethod
    async def autocomplete(cls, interaction: discord.Interaction, value: str) -> list[discord.app_commands.Choice[str]]:
        choices = []
        for name, tzinfo in ALL_TIMEZONES.items():
            if name.lower().startswith(value.lower()):
                choices.append(discord.app_commands.Choice(name=name, value=tzinfo.key))

        return choices[:25]
