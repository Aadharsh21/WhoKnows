"""WhoKnows on Discord.

Runs the demo team as live agents in a Discord server. Each person DMs the bot,
takes a seat ("seat nina"), and from then on talks to their own agent. Seats
nobody takes are played by simulated teammates. Three channels show the rest:

  #backchannel   every message between agents, and everything a gate blocked
  #team-board    the team board after each check
  #teammates     what the simulated teammates see on their phones

    pip install -r requirements-bot.txt
    DISCORD_BOT_TOKEN=...  python3 -m whoknows.bot

Optional: ANTHROPIC_API_KEY lets agents understand free-form messages and draft
changes the demo has no recipe for. WHOKNOWS_GUILD_ID picks the server when the
bot is in more than one.
"""

from __future__ import annotations

import asyncio
import os
import sys

import discord

from .live import Live, Out

CHANNELS = ("backchannel", "team-board", "teammates")
LAMP = 0xFFC46B


def _clip(text: str, limit: int = 1900) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


class Choices(discord.ui.View):
    def __init__(self, bot: "WhoKnowsBot", qid: str, options: list):
        super().__init__(timeout=None)
        self.bot, self.qid = bot, qid
        for value, label in options:
            button = discord.ui.Button(label=label[:80], style=discord.ButtonStyle.primary, custom_id=f"{qid}:{value}")
            button.callback = self._pick(value, label)
            self.add_item(button)

    def _pick(self, value: str, label: str):
        async def callback(interaction: discord.Interaction):
            async with self.bot.lock:
                result = self.bot.live.answer(interaction.user.id, self.qid, value)
            for child in self.children:
                child.disabled = True
                if getattr(child, "custom_id", "") == f"{self.qid}:{value}":
                    child.style = discord.ButtonStyle.success
            await interaction.response.edit_message(
                content=_clip(f"{interaction.message.content}\n> {result}"), view=self)
            await self.bot.flush()
        return callback


class WhoKnowsBot(discord.Client):
    def __init__(self, live: Live, guild_id: int | None = None):
        super().__init__(intents=discord.Intents.default())
        self.live = live
        self.guild_id = guild_id
        self.channels_by_name: dict[str, discord.TextChannel] = {}
        self.lock = asyncio.Lock()

    async def on_ready(self):
        guild = self.get_guild(self.guild_id) if self.guild_id else (self.guilds[0] if self.guilds else None)
        if guild is None:
            print("The bot isn't in a server yet. Invite it, then restart.", file=sys.stderr)
            return
        for name in CHANNELS:
            channel = discord.utils.get(guild.text_channels, name=name)
            if channel is None:
                try:
                    channel = await guild.create_text_channel(name)
                except discord.Forbidden:
                    print(f"No #{name} channel and no permission to create it; skipping it.", file=sys.stderr)
                    continue
            self.channels_by_name[name] = channel
        print(f"WhoKnows is live in {guild.name}. DM the bot and say: seat nina")

    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is not None:
            return
        async with self.lock:
            reply = self.live.handle(message.author.id, message.content)
        if reply:
            await message.channel.send(_clip(reply))
        await self.flush()

    def _card(self, card: dict) -> discord.Embed:
        owner = self.live.name(card["owner"])
        embed = discord.Embed(title=f"{owner}'s {card['path']}  +{card['added']} -{card['removed']}",
                              description=_clip(card.get("message", ""), 300), color=LAMP)
        if card.get("diff"):
            embed.add_field(name="The change", value=f"```diff\n{_clip(card['diff'], 950)}\n```", inline=False)
        elif card.get("held_back"):
            embed.add_field(name="The change", value=card["held_back"], inline=False)
        return embed

    async def flush(self):
        async with self.lock:
            items, self.live.out = self.live.out, []
        batches: dict[str, list[str]] = {}
        for item in items:
            if item.kind == "dm":
                await self._dm(item)
            elif item.card:
                await self._post(item.to, item.text, embed=self._card(item.card))
            else:
                batches.setdefault(item.to, []).append(item.text)
        for name, lines in batches.items():
            chunk = ""
            for line in lines:
                if len(chunk) + len(line) + 1 > 1900:
                    await self._post(name, chunk)
                    chunk = ""
                chunk += line + "\n"
            if chunk:
                await self._post(name, chunk)

    async def _post(self, name: str, text: str, embed=None):
        channel = self.channels_by_name.get(name)
        if channel:
            await channel.send(_clip(text), embed=embed)

    async def _dm(self, item: Out):
        user = self.get_user(item.to) or await self.fetch_user(item.to)
        text = item.text
        if item.diffs:
            blocks = "\n".join(f"```diff\n{_clip(d, 700)}\n```" for d in item.diffs.values())
            text = f"{text}\n{blocks}"
        view = Choices(self, item.question, item.options) if item.question else None
        embed = self._card(item.card) if item.card else None
        await user.send(_clip(text), embed=embed, view=view)


def main() -> int:
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        print("Set DISCORD_BOT_TOKEN first. See the README for setting up the bot.", file=sys.stderr)
        return 1
    ai = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            ai = anthropic.Anthropic()
        except ImportError:
            print("ANTHROPIC_API_KEY is set but the anthropic package isn't installed; using rules only.",
                  file=sys.stderr)
    guild = os.environ.get("WHOKNOWS_GUILD_ID")
    WhoKnowsBot(Live(ai=ai), guild_id=int(guild) if guild else None).run(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
