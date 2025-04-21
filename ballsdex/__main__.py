import threading
import signal
import asyncio
import sys
from flask import Flask
from ballsdex.__main__ import bot  # Import the BallsDex bot

app = Flask(__name__)

@app.route('/')
def home():
    return "BallsDex is running!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

async def shutdown_handler(bot):
    log.info("Shutting down bot...")
    await bot.close()
    log.info("Bot shut down successfully.")

def run_bot():
    bot.run()

def shutdown(signum, frame):
    asyncio.ensure_future(shutdown_handler(bot))
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)  # Handling Ctrl+C to shut down both bot and server
    signal.signal(signal.SIGTERM, shutdown)  # Handling termination signal

    # Start Flask in a separate thread
    threading.Thread(target=run_web, daemon=True).start()

    # Start Discord bot
    run_bot()
