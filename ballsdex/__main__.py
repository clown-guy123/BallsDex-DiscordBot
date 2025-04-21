import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from signal import SIGTERM
from threading import Thread

from flask import Flask
import discord
from rich import print
from tortoise import Tortoise

from ballsdex import __version__ as bot_version
from ballsdex.core.bot import BallsDexBot
from ballsdex.logging import init_logger
from ballsdex.settings import read_settings, settings, update_settings, write_default_settings

# Flask app
app = Flask(__name__)

@app.route("/")
def home():
    return "BallsDex Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

discord.voice_client.VoiceClient.warn_nacl = False
log = logging.getLogger("ballsdex")

TORTOISE_ORM = {
    "connections": {"default": os.environ.get("BALLSDEXBOT_DB_URL")},
    "apps": {
        "models": {
            "models": ["ballsdex.core.models"],
            "default_connection": "default",
        },
    },
}

class CLIFlags(argparse.Namespace):
    version: bool
    config_file: Path
    reset_settings: bool
    disable_rich: bool
    disable_message_content: bool
    disable_time_check: bool
    skip_tree_sync: bool
    debug: bool
    dev: bool

def parse_cli_flags(arguments: list[str]) -> CLIFlags:
    parser = argparse.ArgumentParser(description="Collect and exchange countryballs on Discord")
    parser.add_argument("--version", "-V", action="store_true")
    parser.add_argument("--config-file", type=Path, default=Path("./config.yml"))
    parser.add_argument("--reset-settings", action="store_true")
    parser.add_argument("--disable-rich", action="store_true")
    parser.add_argument("--disable-message-content", action="store_true")
    parser.add_argument("--disable-time-check", action="store_true")
    parser.add_argument("--skip-tree-sync", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dev", action="store_true")
    return parser.parse_args(arguments, namespace=CLIFlags())

def reset_settings_func(path: Path):
    write_default_settings(path)
    print(f"[green]New settings written at [blue]{path}[/blue].[/green]")
    print("[yellow]Set your [bold]discord-token[/bold] and restart the bot.[/yellow]")
    sys.exit(0)

def print_welcome():
    print(f"[green]{settings.bot_name} bot[/green]")
    print(f" [red]Bot version:[/red] [yellow]{bot_version}[/yellow]")
    print(f" [red]Discord.py version:[/red] [yellow]{discord.__version__}[/yellow]")

async def init_tortoise():
    log.debug(f"Initializing Tortoise ORM with DB: {os.environ.get('BALLSDEXBOT_DB_URL')}")
    await Tortoise.init(config=TORTOISE_ORM)

async def shutdown_handler(bot: BallsDexBot, signal_type: str | None = None):
    if signal_type:
        log.info(f"Received {signal_type}, stopping bot...")
    try:
        await asyncio.wait_for(bot.close(), timeout=10)
    finally:
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        [task.cancel() for task in pending]
        try:
            await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=5)
        except asyncio.TimeoutError:
            log.error("Timeout while cancelling tasks.")
        sys.exit(0 if signal_type else 1)

def global_exception_handler(bot: BallsDexBot, loop: asyncio.AbstractEventLoop, context: dict):
    exc = context.get("exception")
    if exc and isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return
    log.critical("Unhandled exception: %s", context["message"], exc_info=exc)

def bot_exception_handler(bot: BallsDexBot, bot_task: asyncio.Future):
    try:
        bot_task.result()
    except (SystemExit, KeyboardInterrupt, asyncio.CancelledError):
        pass
    except Exception as exc:
        log.critical("Main bot task crashed", exc_info=exc)
        asyncio.create_task(shutdown_handler(bot))

def main():
    cli_flags = parse_cli_flags(sys.argv[1:])
    if cli_flags.version:
        print(f"BallsDex Bot Version: {bot_version}")
        sys.exit(0)
    if cli_flags.reset_settings:
        reset_settings_func(cli_flags.config_file)
    read_settings(cli_flags.config_file)
    update_settings(cli_flags)
    if not settings.discord_token:
        print("[red]Missing Discord token. Check your config file.[/red]")
        sys.exit(1)
    init_logger(debug=cli_flags.debug, rich=not cli_flags.disable_rich)
    print_welcome()

    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    bot = BallsDexBot(cli_flags)
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(lambda l, c: global_exception_handler(bot, l, c))
    bot_task = loop.create_task(bot.start_bot())
    bot_task.add_done_callback(lambda t: bot_exception_handler(bot, t))

    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(shutdown_handler(bot))

if __name__ == "__main__":
    main()
