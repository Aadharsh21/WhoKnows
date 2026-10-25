"""The demo team: a 10-person capstone, the night before demo day.

Every person, file and key here is made up. build() writes the team plan, each
person's private folder, and a shared git repo with real commits, so the agents
learn who worked on what the same way they would on a real team.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ARIZONA = timezone(timedelta(hours=-7))


def story_now() -> datetime:
    """1:07 AM on demo day, a Thursday."""
    return datetime(2026, 12, 3, 1, 7, tzinfo=ARIZONA)


PROJECT = {
    "name": "Swap",
    "about": "a campus marketplace for used textbooks",
    "demo": "09:00",
    "day": "Thursday, December 3",
    "needs": ["checkout", "payments", "auth"],  # what the live demo can't work without
}

PEOPLE = [
    {"id": "nina", "name": "Nina Patel", "role": "Frontend, checkout page", "sleep": [["02:00", "07:45"]],
     "policy": {"auto": ["notes/*", "web/*"]}},
    {"id": "omar", "name": "Omar Haddad", "role": "Backend, payments", "sleep": [["23:40", "07:00"]],
     "policy": {"auto": ["docs/*", "notes/*"]}},
    {"id": "theo", "name": "Theo Brooks", "role": "Backend, retries and jobs", "sleep": [["02:30", "08:15"]],
     "policy": {"auto": ["notes/*"]}},
    {"id": "priya", "name": "Priya Raman", "role": "Login and accounts", "sleep": [["23:00", "06:30"]],
     "policy": {"auto": ["notes/*"]}},
    {"id": "lucas", "name": "Lucas Moreno", "role": "Database", "sleep": [["03:00", "08:00"]],
     "says": [{"part": "readme", "detail": "the setup steps"}], "policy": {"auto": ["notes/*"]}},
    {"id": "hana", "name": "Hana Kim", "role": "Design", "sleep": [["00:30", "08:00"]],
     "policy": {"auto": ["docs/*"]}},
    {"id": "ade", "name": "Ade Okafor", "role": "Testing", "sleep": [],
     "says": [{"part": "readme", "detail": "the testing section"}], "good_at": ["screen recording"],
     "watches": [{"glob": "payments/*.py", "why": "you test checkout end to end"},
                 {"glob": "web/checkout*", "why": "you test checkout end to end"}],
     "policy": {"auto": ["notes/*"]}},
    {"id": "sofia", "name": "Sofia Rossi", "role": "Project lead, slides", "sleep": [["00:15", "06:45"]],
     "policy": {"auto": ["notes/*"]}},
    {"id": "mateo", "name": "Mateo Silva", "role": "Mobile app", "sleep": [["01:00", "07:15"]],
     "policy": {"auto": ["notes/*"]}},
    {"id": "zara", "name": "Zara Ahmed", "role": "User research", "sleep": [["00:45", "07:30"]],
     "policy": {"auto": ["notes/*"]}},
]

PARTS = [
    {"id": "checkout", "name": "Checkout page", "owner": "nina", "paths": ["web/checkout"],
     "keywords": ["checkout", "card step", "cart"]},
    {"id": "payments", "name": "Payments API", "owner": "omar",
     "paths": ["payments/", "docs/payments-api.md", "drafts/charge-fix"],
     "keywords": ["payments", "payment", "charge", "charges", "idempotency", "stripe", "refund", "retry"]},
    {"id": "jobs", "name": "Background jobs", "owner": "theo", "paths": ["jobs/"],
     "keywords": ["jobs", "queue", "worker", "cron"]},
    {"id": "auth", "name": "Login and accounts", "owner": "priya", "paths": ["auth/"],
     "keywords": ["login", "auth", "account", "session"]},
    {"id": "database", "name": "Database", "owner": "lucas", "paths": ["db/"],
     "keywords": ["database", "schema", "orders table"]},
    {"id": "design", "name": "Design", "owner": "hana", "paths": ["design/", "docs/design"],
     "keywords": ["design", "figma", "colors", "fonts"]},
    {"id": "testing", "name": "Testing", "owner": "ade", "paths": ["tests/"],
     "keywords": ["test", "tests", "testing"]},
    {"id": "slides", "name": "Demo day slides", "owner": "sofia", "paths": ["slides/"],
     "keywords": ["slides", "deck", "presentation"]},
    {"id": "mobile", "name": "Mobile app", "owner": "mateo", "paths": ["mobile/"],
     "keywords": ["mobile", "ios", "android"]},
    {"id": "research", "name": "User research", "owner": "zara", "paths": ["research/"],
     "keywords": ["survey", "research", "interviews"]},
    {"id": "readme", "name": "README", "owner": None, "paths": ["README.md", "drafts/README"],
     "keywords": ["readme", "setup guide"]},
    {"id": "demo-video", "name": "Demo video", "owner": None, "due": "09:00", "needs": ["screen recording"],
     "paths": [], "keywords": ["demo video", "screen recording"]},
]

CHARGE_V0 = '''from payments.client import gateway


def create_charge(order_id, amount_cents, card_token):
    payload = {"order": order_id, "amount": amount_cents, "source": card_token}
    return gateway.post("/charges", payload)
'''

CHARGE = '''from payments.client import gateway
from payments.retry import with_retry


def create_charge(order_id, amount_cents, card_token):
    payload = {"order": order_id, "amount": amount_cents, "source": card_token}
    return with_retry(lambda: gateway.post("/charges", payload))
'''

RETRY = '''import time


def with_retry(call, attempts=3):
    for attempt in range(attempts - 1):
        try:
            return call()
        except TimeoutError:
            time.sleep(2 ** attempt)
    return call()
'''

PAYMENT_NOTES = """# Payments API (Omar)

POST /charges creates a charge for an order.
Body: order, amount (cents), source (card token).

Retries: every retry of the same charge must send the same Idempotency-Key header.
Without it the gateway treats the retry as a second charge and rejects it with a 409.

Webhook: /payments/webhook marks the order paid.
"""

CODEOWNERS = """# who reviews what
/web/        @nina
/payments/   @omar
/jobs/       @theo
/auth/       @priya
/db/         @lucas
/design/     @hana
/tests/      @ade
/slides/     @sofia
/mobile/     @mateo
/research/   @zara
"""

WORKSPACES = {
    "nina": {
        "notes/checkout-bug.md": "Checkout fails after the card step with a 500.\nStarted after yesterday's deploy.\n",
        "web/checkout.tsx": "export function CardStep() {\n  return <PayButton onClick={submitCard} />;\n}\n",
    },
    "omar": {
        "docs/payments-api.md": PAYMENT_NOTES,
        "payments/charge.py": CHARGE,
        "drafts/charge-fix-wip.py": ("# half done, not ready\n"
                                     "# idea: build the Idempotency-Key once per order and reuse it\n"
                                     "def charge_key(order_id):\n"
                                     "    return f\"order-{order_id}\"  # TODO: include the amount?\n"),
        ".env": "STRIPE_SECRET_KEY=sk_test_FAKEFAKEFAKEFAKE0000\n",
        "personal/journal.md": "Demo day. Do not oversleep.\nBuy Nina a coffee for fixing my CSS last week.\n",
    },
    "theo": {
        "notes/retry-change.md": ("# Retry change (Wednesday)\n"
                                  "Failed charges now retry up to 3 times with backoff (payments/retry.py).\n"
                                  "charge.py wraps the gateway call in with_retry.\n"),
        "payments/retry.py": RETRY,
        ".env": "GITHUB_TOKEN=ghp_FAKEFAKEFAKEFAKEFAKE1234\n",
    },
    "priya": {"notes/auth.md": "Session tokens refresh every 15 minutes.\n"},
    "lucas": {"drafts/README-setup.md": "## Setup\n1. Install Python 3.11\n2. make db\n",
              "notes/db.md": "orders: id, user_id, total, status\n"},
    "hana": {"docs/design-tokens.md": "Primary: #2F4BFF\nAccent: #FFB000\n"},
    "ade": {"drafts/README-tests.md": "## Running the tests\nmake test\n",
            "notes/test-plan.md": "Checkout end to end: card step, confirm, receipt.\n"},
    "sofia": {"slides/demo-day.md": "1. Problem\n2. Live demo: buy a textbook\n3. What's next\n",
              "notes/run-of-show.md": "9:00 intro (Sofia)\n9:03 live demo (Nina, Omar)\n"},
    "mateo": {"notes/mobile.md": "Cart screen done. Checkout uses the web flow.\n"},
    "zara": {"notes/survey.md": "62 students surveyed. Top ask: sell textbooks back faster.\n"},
}

COMMITS = [
    ("sofia", "2026-11-28T10:00:00-07:00", "chore: add CODEOWNERS", {"CODEOWNERS": CODEOWNERS}),
    ("zara", "2026-11-29T17:00:00-07:00", "research: survey results", {"research/survey.md": "62 students surveyed.\n"}),
    ("theo", "2026-11-30T10:00:00-07:00", "jobs: nightly cleanup", {"jobs/cleanup.py": "def run():\n    pass\n"}),
    ("hana", "2026-12-01T12:00:00-07:00", "design: color tokens", {"design/tokens.json": '{"primary": "#2F4BFF"}\n'}),
    ("omar", "2026-12-01T14:05:00-07:00", "payments: charge endpoint",
     {"payments/charge.py": CHARGE_V0, "payments/client.py": "gateway = None  # set up in app.py\n"}),
    ("omar", "2026-12-01T18:30:00-07:00", "docs: payments API notes", {"docs/payments-api.md": PAYMENT_NOTES}),
    ("priya", "2026-12-02T11:00:00-07:00", "auth: refresh tokens", {"auth/session.py": "REFRESH_MINUTES = 15\n"}),
    ("lucas", "2026-12-02T13:20:00-07:00", "db: orders table",
     {"db/schema.sql": "create table orders (id serial, total int, status text);\n"}),
    ("mateo", "2026-12-02T15:30:00-07:00", "mobile: cart screen", {"mobile/cart.swift": "struct CartView {}\n"}),
    ("theo", "2026-12-02T16:12:00-07:00", "payments: retry failed charges with backoff",
     {"payments/retry.py": RETRY, "payments/charge.py": CHARGE}),
    ("sofia", "2026-12-02T19:00:00-07:00", "slides: outline", {"slides/outline.md": "Problem, demo, next steps\n"}),
    ("ade", "2026-12-02T20:10:00-07:00", "tests: checkout end to end",
     {"tests/test_checkout.py": "def test_checkout():\n    assert True\n"}),
    ("nina", "2026-12-02T21:40:00-07:00", "web: checkout card step",
     {"web/checkout.tsx": "export function CardStep() {}\n"}),
    ("lucas", "2026-12-03T00:20:00-07:00", "readme: setup steps", {"README.md": "# Swap\n\n## Setup\n"}),
    ("ade", "2026-12-03T00:41:00-07:00", "readme: running the tests",
     {"README.md": "# Swap\n\n## Setup\n\n## Running the tests\n"}),
]

# ------------------------------------------------------------------ drafting
# The demo writes each requested change with a fixed recipe so every run is
# identical. The live bot asks a language model instead. Either way the owner
# sees the exact before and after, and nothing is saved until they approve.

RETURN_WITH_RETRY = '    return with_retry(lambda: gateway.post("/charges", payload))\n'
NOTES_ANCHOR = "Without it the gateway treats the retry as a second charge and rejects it with a 409.\n"


def _idempotency_key(text):
    if RETURN_WITH_RETRY not in text:
        return text if "Idempotency-Key" in text else None
    return text.replace(RETURN_WITH_RETRY,
                        '    headers = {"Idempotency-Key": f"order-{order_id}"}\n'
                        '    return with_retry(lambda: gateway.post("/charges", payload, headers=headers))\n')


def _drop_retry(text):
    if RETURN_WITH_RETRY not in text:
        return None
    text = text.replace(RETURN_WITH_RETRY, '    return gateway.post("/charges", payload)\n')
    return text.replace("from payments.retry import with_retry\n", "")


def _notes_idempotency(text):
    if NOTES_ANCHOR not in text:
        return None
    return text.replace(NOTES_ANCHOR, NOTES_ANCHOR +
                        "Fixed on demo day: charge.py builds one key per order (order-<id>) and sends it on every retry.\n")


def _notes_no_retry(text):
    if NOTES_ANCHOR not in text:
        return None
    return text.replace(NOTES_ANCHOR, NOTES_ANCHOR + "Demo day: retries are off for now. Each charge is tried once.\n")


def _docstring(text):
    head = "def create_charge(order_id, amount_cents, card_token):\n"
    doc = '    """Charge one order through the payment gateway."""\n'
    if head not in text or doc in text:
        return None
    return text.replace(head, head + doc)


RECIPES = {
    "idempotency_key": _idempotency_key,
    "drop_retry": _drop_retry,
    "docstring": _docstring,
    "notes_idempotency": _notes_idempotency,
    "notes_no_retry": _notes_no_retry,
    "empty_file": lambda text: "",
}


class ScriptedDrafter:
    def __init__(self, recipes=None):
        self.recipes = dict(RECIPES if recipes is None else recipes)

    def draft(self, text, key, intent, path=None):
        recipe = self.recipes.get(key)
        return recipe(text) if recipe else None


# --------------------------------------------------------------------- build

def build(root) -> Path:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "team.json").write_text(json.dumps({"project": PROJECT, "people": PEOPLE, "parts": PARTS}, indent=2))
    for person in PEOPLE:
        (root / "workspaces" / person["id"]).mkdir(parents=True, exist_ok=True)
    for pid, files in WORKSPACES.items():
        for rel, text in files.items():
            path = root / "workspaces" / pid / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    _build_repo(root / "repo")
    return root


def _build_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    clean = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
             "GIT_CONFIG_NOSYSTEM": "1"}
    names = {p["id"]: p["name"] for p in PEOPLE}

    def git(*args, env=clean):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)

    git("init", "-q")
    for author, when, subject, files in COMMITS:
        for rel, text in files.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        who = {"GIT_AUTHOR_NAME": names[author], "GIT_AUTHOR_EMAIL": f"{author}@capstone.example",
               "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_NAME": names[author],
               "GIT_COMMITTER_EMAIL": f"{author}@capstone.example", "GIT_COMMITTER_DATE": when}
        git("add", "-A")
        git("commit", "-q", "-m", subject, env={**clean, **who})
