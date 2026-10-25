# WhoKnows Discord bot — Railway worker (no HTTP port needed)
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

# The demo builds a miniature Git repository when the bot starts.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-bot.txt ./
RUN python -m pip install --no-cache-dir -r requirements-bot.txt
COPY whoknows/ ./whoknows/

CMD ["python", "-m", "whoknows.bot"]
