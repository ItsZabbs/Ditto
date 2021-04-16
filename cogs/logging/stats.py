import asyncio
from collections import namedtuple

import asyncpg  # type: ignore
from discord.ext import commands, menus, tasks  # type: ignore
from donphan import Column, Table, SQLType  # type: ignore

from ditto import BotBase, Cog, Context
from ditto.utils import EmbedPaginator


class Commands(Table, schema="logging"):  # type: ignore
    message_id: SQLType.BigInt = Column(primary_key=True)  # type: ignore
    guild_id: SQLType.BigInt = Column(index=True)  # type: ignore
    channel_id: SQLType.BigInt = Column(index=True)  # type: ignore
    user_id: SQLType.BigInt = Column(index=True)  # type: ignore
    invoked_at: SQLType.Timestamp  # type: ignore
    prefix: SQLType.Text  # type: ignore
    command: SQLType.Text  # type: ignore
    failed: SQLType.Boolean  # type: ignore


CommandInvoke = namedtuple("CommandInvoke", (column.name for column in Commands._columns))  # type: ignore


class Stats(Cog):
    def __init__(self, bot: BotBase) -> None:
        super().__init__(bot)
        self._batch_lock = asyncio.Lock()
        self._batch_data: list[CommandInvoke] = []

        self.bulk_insert.add_exception_type(asyncpg.exceptions.PostgresConnectionError)
        self.bulk_insert.start()

    async def cog_check(self, ctx: Context) -> bool:
        return await commands.is_owner().predicate(ctx)  # type: ignore

    @commands.command()
    async def command_history(self, ctx: Context) -> None:
        embed = EmbedPaginator(colour=ctx.me.colour, max_fields=10).set_author(
            name="Command History:", icon_url=self.bot.user.avatar_url  # type: ignore
        )

        commands = await Commands.fetch(order_by="invoked_at DESC", limit=100)
        if commands:
            for command in commands:
                user = self.bot.get_user(command["user_id"]) or "Unknown user"
                embed.add_field(
                    name=f'{user} ({command["user_id"]}) @ {command["invoked_at"]}',
                    value=f'`{command["prefix"]}{command["command"]}`',
                    inline=False,
                )
        else:
            embed.add_line("No commands used.")

        await menus.MenuPages(embed).start(ctx)

    @commands.Cog.listener("on_command_completion")
    @commands.Cog.listener("on_command_error")
    async def on_command(self, ctx: Context, error: BaseException = None) -> None:
        command = ctx.command

        if command is None:
            return

        guild_id = getattr(ctx.guild, "id", None)

        invoke = CommandInvoke(  # type: ignore
            ctx.message.id,
            guild_id,
            ctx.channel.id,
            ctx.author.id,
            ctx.message.created_at,
            ctx.prefix,
            command.qualified_name,
            ctx.command_failed,
        )

        async with self._batch_lock:
            self._batch_data.append(invoke)

    @tasks.loop(seconds=15)
    async def bulk_insert(self) -> None:
        async with self._batch_lock:
            if self._batch_data:
                await Commands.insert_many(Commands._columns, *self._batch_data)
                self._batch_data.clear()


def setup(bot: BotBase):
    bot.add_cog(Stats(bot))
