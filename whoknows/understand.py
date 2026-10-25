"""Turning what a person types into something their agent can do.

Plain rules cover the ways people usually ask, with no API key needed. If
ANTHROPIC_API_KEY is set, Claude Haiku reads anything the rules miss into the
same small set of actions. Either way the result is only a request: the agents'
rules still decide what is shared, asked, or changed.
"""

from __future__ import annotations

import json
import re

from .cards import parts_in

ACTIONS = ("who_knows", "question", "pass_on", "fetch", "file", "help", "change", "time", "claim",
           "seat", "clock", "board", "check", "status", "reset", "help_text", "unknown")

HELP = """Things you can say to your agent:
- who knows the payments code?
- why would a retry get a 409?   (answered from teammates' shareable notes, with sources)
- pass it on                     (sends your last question to the person most likely to know)
- get omar's notes on payments
- ask omar for drafts/charge-fix-wip.py
- can theo hop on a call?
- ask omar's agent to send the same idempotency key on every retry in charge.py
- i need 10 min with omar before the demo
- i'm doing the readme tonight
Demo controls: seat <name>, seats, board, check (runs the team board check), skip to 7:00, status, reset"""

# A file someone names: payments/charge.py, notes/retry-change.md, or a dotfile like .env, which people
# ask for by name too (the policy keeps it private; it has to be understood before it can be refused).
PATH = re.compile(r"(?<![\w/])((?:[\w-]+/)*(?:[\w.-]+\.(?:py|md|tsx|ts|js|json|sql|swift|txt|csv|yml|yaml|pem|key)"
                  r"|\.env(?:\.[\w-]+)?))\b")
RECIPE_HINTS = (
    (re.compile(r"(?i)idempotency|same key|one key"), "idempotency_key"),
    (re.compile(r"(?i)(?:drop|remove|turn off|disable|no)\s+(?:the\s+)?retr"), "drop_retry"),
)


def _people(team):
    return {p["name"].split()[0].lower(): p["id"] for p in team["people"]} | {p["id"]: p["id"] for p in team["people"]}


def _named(text, team, exclude=None):
    names = _people(team)
    for word in re.findall(r"[a-z]+", text.lower()):
        # "omars agent" is how people type "omar's agent" on a phone, so a possessive without the apostrophe counts.
        pid = names.get(word) or (names.get(word[:-1]) if word.endswith("s") else None)
        if pid and pid != exclude:
            return pid
    return None


def _time_of(text, demo="09:00"):
    m = re.search(r"before\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text, re.I)
    if not m:
        return demo if re.search(r"before (?:the )?demo", text, re.I) else demo
    hour, minute, half = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if half == "pm" and hour < 12:
        hour += 12
    if half == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def recipe_for(text: str) -> str | None:
    return next((key for pattern, key in RECIPE_HINTS if pattern.search(text)), None)


def by_rules(text: str, me: str | None, team: dict) -> dict:
    t = text.strip()
    low = t.lower()
    parts = team["parts"]
    demo = team.get("project", {}).get("demo", "09:00")

    m = re.fullmatch(r"(?:seat|sit as|play as|i'?m|i am)\s+([a-z]+)[.!]?", low)
    if m and m.group(1) in _people(team):
        return {"action": "seat", "person": _people(team)[m.group(1)]}
    if low in ("seats", "who's here", "whos here"):
        return {"action": "status"}
    m = re.fullmatch(r"(?:time|clock|skip to|go to|jump to|fast forward to)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", low)
    if m:
        return {"action": "clock", "before": _time_of(f"before {m.group(1)}:{m.group(2) or '00'} {m.group(3) or ''}")}
    if low in ("morning", "skip to morning", "fast forward"):
        return {"action": "clock", "before": "07:00"}
    if low in ("board", "team board", "who's doing what", "whos doing what"):
        return {"action": "board"}
    if low in ("check", "board check", "team check"):
        return {"action": "check"}
    if low in ("status", "who's awake", "whos awake", "who is awake"):
        return {"action": "status"}
    if low in ("reset", "start over"):
        return {"action": "reset"}
    if low in ("help", "?", "commands", "what can you do"):
        return {"action": "help_text"}

    m = re.search(r"\b(?:i'?m|i am)\s+(?:doing|writing|taking|on|handling|working on)\s+(?:the\s+)?(.+?)(?:\s+tonight)?[.!]?$", low)
    if m and parts_in(m.group(1), parts):
        return {"action": "claim", "part": parts_in(m.group(1), parts)[0], "detail": m.group(1)}

    who = _named(t, team, exclude=me)
    path = PATH.search(t)

    m = re.search(r"(\d+)\s*(?:min|mins|minutes)\b", low)
    if m and who and re.search(r"\bwith\b", low):
        return {"action": "time", "person": who, "minutes": int(m.group(1)), "before": _time_of(t, demo), "about": t}

    if who and path and re.search(r"\b(?:ask|tell|get|have)\b.*\bto\b", low) and re.search(
            r"\b(?:change|make|send|add|drop|remove|fix|update|rename|turn|use|set)\b", low):
        intent = re.sub(r"(?i)^.*?\bto\b\s+", "", t, count=1)
        return {"action": "change", "person": who, "path": path.group(1), "intent": intent, "recipe": recipe_for(t)}

    if who and re.search(r"\b(?:hop on|jump on|get on|call|help me|look at)\b", low):
        return {"action": "help", "person": who, "minutes": 15, "about": t, "part": (parts_in(t, parts) or [None])[0]}

    if who and path and re.search(r"\b(?:ask|get|send|share|grab|want|need)\b", low):
        return {"action": "file", "person": who, "path": path.group(1)}

    if who and re.search(r"\b(?:notes|docs|anything|stuff|info)\b", low):
        return {"action": "fetch", "person": who, "part": (parts_in(t, parts) or [None])[0]}

    if re.fullmatch(r"(?:pass (?:it|that|this) on|ask them(?: directly)?|pass it to them|send it to them)[.!]?", low):
        return {"action": "pass_on"}
    if re.search(r"\b(?:who|anyone|anybody)\b", low):
        return {"action": "who_knows", "question": t}
    if t.endswith("?") or re.match(r"(?:why|what|how|when|where|which|does|do|is|are|can|should)\b", low):
        return {"action": "question", "question": t}
    if parts_in(t, parts):
        return {"action": "who_knows", "question": t}
    return {"action": "unknown"}


SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": [a for a in ACTIONS if a not in ("seat", "clock", "reset", "check")]},
        "person": {"type": "string", "description": "first name of the teammate the request is about, or empty"},
        "path": {"type": "string", "description": "file path or file name mentioned, or empty"},
        "part": {"type": "string", "description": "part id from the list, or empty"},
        "minutes": {"type": "integer"},
        "before": {"type": "string", "description": "HH:MM in 24-hour time, or empty"},
        "intent": {"type": "string", "description": "for change requests: the change, in the person's words"},
    },
    "required": ["action"],
    "additionalProperties": False,
}


class Understander:
    def __init__(self, client=None, model: str = "claude-haiku-5-5"):
        self.client = client
        self.model = model

    def parse(self, text: str, me: str | None, team: dict) -> dict:
        result = by_rules(text, me, team)
        if result["action"] == "unknown" and self.client:
            try:
                result = self._ask_model(text, me, team) or result
            except Exception:
                pass
        return result

    def _ask_model(self, text, me, team):
        people = "\n".join(f"- {p['name'].split()[0]}: {p['role']}" for p in team["people"])
        parts = "\n".join(f"- {p['id']}: {p['name']}" for p in team["parts"])
        system = (
            "You route one message a student typed to their own team agent. Pick the single best action.\n"
            "who_knows: they want to find who works on or knows about something.\n"
            "question: they ask a factual question about the project that a teammate's notes might answer.\n"
            "pass_on: they want their last question sent to the teammate most likely to know.\n"
            "fetch: they want a teammate's shareable notes about a part.\n"
            "file: they want a specific file from a teammate.\n"
            "help: they want a teammate's time right now (a call, a look).\n"
            "change: they want a teammate's file changed; put the change in intent.\n"
            "time: they want time with a teammate before a deadline.\n"
            "claim: they say they're doing a part.\n"
            "board, status, help_text: questions about the team board, who's awake, or what the agent can do.\n"
            "unknown: none of these.\n"
            f"Team:\n{people}\nParts:\n{parts}")
        sender = next((p["name"].split()[0] for p in team["people"] if p["id"] == me), "someone")
        response = self.client.messages.create(
            model=self.model, max_tokens=400, system=system,
            messages=[{"role": "user", "content": f"{sender} typed: {text}"}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
        raw = next((b.text for b in response.content if getattr(b, "type", "") == "text"), "")
        data = json.loads(raw)
        action = data.get("action")
        if action not in ACTIONS:
            return None
        names = _people(team)
        out = {"action": action}
        if data.get("person"):
            out["person"] = names.get(data["person"].lower())
        if data.get("path"):
            out["path"] = data["path"]
        if data.get("part") in {p["id"] for p in team["parts"]}:
            out["part"] = data["part"]
        out["minutes"] = int(data.get("minutes") or 15)
        out["before"] = data.get("before") or team.get("project", {}).get("demo", "09:00")
        out["intent"] = data.get("intent") or text
        out["about"] = text
        out["question"] = text
        out["recipe"] = recipe_for(text)
        if action in ("fetch", "file", "help", "change", "time") and not out.get("person"):
            return None
        return out
