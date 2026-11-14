"""burg.nr link shortener bot.

DM the bot a link and it replies with a short one:
    example.com/some/long/link            -> random short link
    example.com/some/long/link my-alias   -> burg.nr/my-alias
    clicks abc12                          -> click count for a short link
    help                                  -> show this help

Slash commands /shorten and /clicks work too (including in DMs when the bot is
installed to your account).
"""
import os
from urllib.parse import quote

import aiohttp
import discord
from discord import app_commands

BASE = "https://burg.nr"
API = f"{BASE}/api"
TOKEN = os.environ["DISCORD_TOKEN"]

HELP = (
    "**burg.nr link shortener** 🍔\n"
    "Send me a link and I'll shorten it.\n"
    "`example.com/long/link` - random short link\n"
    "`example.com/long/link my-alias` - pick your own ending\n"
    "`clicks abc12` - see how many clicks a short link has"
)


async def api_call(session: aiohttp.ClientSession, method: str, path: str, **kwargs):
    """Call the burg.nr API and return the parsed JSON, or an error dict."""
    try:
        async with session.request(method, f"{API}{path}", timeout=aiohttp.ClientTimeout(total=15), **kwargs) as r:
            return await r.json(content_type=None)
    except (aiohttp.ClientError, ValueError, TimeoutError):
        return {"ok": False, "error": "Couldn't reach burg.nr. Try again later."}


async def shorten(session, url: str, alias: str | None = None) -> str:
    payload = {"url": url}
    if alias:
        payload["alias"] = alias
    d = await api_call(session, "POST", "/shorten", json=payload)
    if d.get("ok"):
        return f"🍔 {d['short']}"
    return f"Couldn't shorten: {d.get('error', 'unknown error')}"


async def clicks(session, text: str) -> str:
    code = text.strip().rstrip("/").rsplit("/", 1)[-1]  # accepts a code or a full short link
    d = await api_call(session, "GET", f"/link/{quote(code)}")
    if d.get("ok"):
        return f"{d['short']} → <{d['url']}>\n**{d['clicks']}** clicks"
    return f"Error: {d.get('error', 'unknown error')}"


class Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.session: aiohttp.ClientSession | None = None

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        await self.tree.sync()

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

    async def on_ready(self):
        print(f"Logged in as {self.user}")

    async def on_message(self, message: discord.Message):
        # Only answer plain DMs, never servers.
        if message.author.bot or message.guild is not None:
            return
        parts = message.content.split()
        if not parts:
            return
        cmd = parts[0].lower().lstrip("/!")
        async with message.channel.typing():
            if cmd == "help":
                reply = HELP
            elif cmd in ("clicks", "stats") and len(parts) > 1:
                reply = await clicks(self.session, parts[1])
            else:
                reply = await shorten(self.session, parts[0], parts[1] if len(parts) > 1 else None)
        await message.reply(reply, mention_author=False, suppress_embeds=True)


bot = Bot()

# Let the slash commands run in servers, DMs, and group DMs, and be installed to a user account.
everywhere = app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
installable = app_commands.allowed_installs(guilds=True, users=True)


@bot.tree.command(name="shorten", description="Shorten a link")
@everywhere
@installable
@app_commands.describe(url="The long link", alias="Your own ending (optional)")
async def shorten_cmd(interaction: discord.Interaction, url: str, alias: str | None = None):
    await interaction.response.defer()
    await interaction.followup.send(await shorten(bot.session, url, alias))


@bot.tree.command(name="clicks", description="See how many clicks a short link has")
@everywhere
@installable
@app_commands.describe(link="The short link or its code")
async def clicks_cmd(interaction: discord.Interaction, link: str):
    await interaction.response.defer()
    await interaction.followup.send(await clicks(bot.session, link), suppress_embeds=True)


bot.run(TOKEN)
