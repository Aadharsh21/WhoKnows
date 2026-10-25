# Running the public Discord demo

The public server is **WhoKnows Sandbox**: https://discord.gg/NdTDPptqSs. The invite never expires.

## For whoever hosts the bot (on a Mac)

1. Get the latest code: `git pull` in your WhoKnows folder.
2. Set up once:

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements-bot.txt
   ```

3. In the Discord Developer Portal, invite the bot to the server with the `bot` scope and the Send Messages, Read Message History and Manage Channels permissions. Copy the server's ID (right-click the server icon, Copy Server ID, with Developer Mode on).
4. Start it. Keep the Mac plugged in with the lid open; `caffeinate -i` stops it from sleeping while the bot runs.

   ```sh
   source .venv/bin/activate
   export DISCORD_BOT_TOKEN=...          # stays on this Mac, never in the repo
   export WHOKNOWS_GUILD_ID=...          # the server ID from step 3
   export ANTHROPIC_API_KEY=...          # optional: lets judges type in their own words
   caffeinate -i python3 -m whoknows.bot
   ```

5. Test with two accounts before sharing the invite: one says `seat nina`, the other `seat omar`.

Everyone on the server shares one night. If nobody writes for 20 minutes, the night starts over at 1:07 AM and every seat frees up, so each new visitor gets a fresh start. `reset` is refused while someone else has written in the last 10 minutes.

## Message to pin in the server

> **WhoKnows: your teammate's asleep. Their agent isn't.**
>
> It's 1:07 AM. A 10-person capstone team demos at 9 AM, checkout is broken, and you're on the team.
>
> 1. DM the WhoKnows bot and say `seat nina`. Other seats: omar, theo, priya, lucas, hana, ade, sofia, mateo, zara.
> 2. Then try:
>    - `who knows the payments code?`
>    - `why would a retry get a 409?`
>    - `ask omar's agent to send the same idempotency key on every retry in charge.py`
>    - `skip to 7:00`
> 3. Bring a friend: one of you takes Nina, the other takes Omar. At 7:00 Omar's agent asks him to approve Nina's change, with buttons.
>
> Watch #backchannel to see every message between the agents, and anything a gate blocked. Seats nobody takes are played by simulated teammates. The night starts over by itself after 20 quiet minutes.
>
> Play the whole night on the site: https://aadharsh21.github.io/WhoKnows/
