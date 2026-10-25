<a href="https://aadharsh21.github.io/WhoKnows/"><img src="docs/readme/hero.png" alt="whoknows. Your teammate's asleep. Their agent isn't." width="100%"></a>

Everyone on the team gets their own AI agent. When you need something, your agent finds **whoever knows about it**, gets what **that person's rules** allow, and **waits for their yes** before touching their files or their time. Nobody gets woken up.

<table>
  <tr>
    <td width="33%" valign="top"><h3>1.2</h3>people notified per question (29 in a group chat)</td>
    <td width="33%" valign="top"><h3>0</h3>pings from an agent to anyone asleep</td>
    <td width="33%" valign="top"><h3>49%</h3>of questions answered on the spot from shared notes</td>
  </tr>
</table>

<a href="#in-numbers">How we measured it</a>

<p>
  <a href="https://aadharsh21.github.io/WhoKnows/"><img src="docs/readme/btn-play.png" alt="Play the night" height="46"></a>
  <a href="https://youtu.be/fG9bHwREPaI"><img src="docs/readme/btn-video.png" alt="Watch the demo video" height="46"></a>
  <a href="https://aadharsh21.github.io/WhoKnows/#rogue"><img src="docs/readme/btn-rogue.png" alt="Watch an agent go rogue" height="46"></a>
  <a href="https://discord.gg/NdTDPptqSs"><img src="docs/readme/btn-discord.png" alt="Try it live in Discord" height="46"></a>
</p>

A 10-person capstone team, the night before demo day. Everything below comes from running the real agents, and at five points you decide for a teammate. In Discord, DM the bot and say `seat nina`, and bring a friend to take Omar's seat. Every step, with the reply you should get, is in [Test it with the demo team](#test-it-with-the-demo-team).

**[Demo video (1:25)](https://youtu.be/fG9bHwREPaI)** · **[How it works](#how-the-agents-decide)** · **[In numbers](#in-numbers)** · **[Rogue agent](#when-an-agent-goes-rogue)** · **[Test it](#test-it-with-the-demo-team)** · **[Code](#run-it-yourself)** · **[Discord](https://discord.gg/NdTDPptqSs)** · [![tests](https://github.com/Aadharsh21/WhoKnows/actions/workflows/tests.yml/badge.svg)](https://github.com/Aadharsh21/WhoKnows/actions/workflows/tests.yml)

Built for the Cubbie Hackathon at DevHacks 2026, Track 2 (agent-to-agent coordination).

## The night

<a href="https://aadharsh21.github.io/WhoKnows/"><img src="docs/readme/night.gif" alt="The night playing on the site: Nina's phone fills with her agent's answers, the lit windows show who's awake, and Omar's phone stays locked while he sleeps." width="100%"></a>

<sub>Recorded from the site, which replays traces from the engine in this repo. Each window is a teammate, and lit means awake. The blue dot above each window is that person's agent. It never goes out.</sub>

1:07 AM. A 10-person capstone team demos at 9:00 AM. Checkout fails after the card step, and Nina doesn't know who wrote the payments code.

1. **Who knows.** Nina's agent asks all nine agents at once. Each checks only its own person's work: the team plan, the repo's CODEOWNERS file, recent commits, and what the person said they're doing. Two answer: Omar owns payments (asleep), and Theo changed the retry code yesterday at 4:12 PM. The other seven just say no.
2. **Answers with sources.** Nina asks why a retry would get a 409. Omar's agent answers for him while he sleeps, quoting his shareable notes word for word and naming the file. Theo's agent quotes his note on the retry change. Together they point at the bug. Omar's draft fix waits for his yes, and his secrets never come up.
3. **Asking first.** Theo is awake, but his agent asks him before offering his time.
4. **No part rests on one person.** At the 1:30 AM team check, the agents compare who's doing what. They split the README between two people who both started it, find a volunteer for the demo video nobody owns, and notice that only Nina knows checkout and only Priya knows login. Ade and Lucas become backups, and their agents pull the shareable notes right away.
5. **Changes as requests.** Nina and Theo each ask Omar's agent to change the same lines of his file, in different ways. Nothing changes. Both wait for Omar.
6. **7:00 AM.** Omar wakes up to a receipt of everything his agent did for him overnight, then a few short questions: which fix (he sees both diffs), whether to share his draft, and one shared slot for the three people who need him before 9. He picks Nina's fix, and his agent offers to let her small changes through next time.
7. **Commits go only where they matter.** The change goes to Nina (she asked), Theo (he changed that code yesterday) and Ade (he tests checkout). The other six never see it. When Omar edits his notes, Nina's agent gets the change too, because those notes were quoted to her.
8. **Trust that grows.** At 7:50 Nina asks for a one-line docstring. Omar said her small changes can go through, so it saves right away. He still gets the commit, with undo one tap away.

At five points you decide for a teammate, and the rest of the night follows from what you picked. All 48 combinations are generated by the engine in this repo.

## Who needs this

On a team of ten, nobody knows who knows what. The answer to "who did the payments code?" is buried in a group chat, the file you need is on someone's laptop, and the one person who can help went to bed two hours ago. So you ping everyone, wake someone up, or wait. Psychologists call a team's sense of who knows what its *transactive memory* (Wegner, 1985): groups work best when each member knows where knowledge lives instead of holding all of it. WhoKnows gives every teammate an agent that is that memory for them.

It's for any group where the person who knows is often busy or asleep:

- **Capstone and senior design.** Eight to twelve people, one demo day, and nobody remembers who wrote which part. That's the night above.
- **Hackathon teams.** Thirty-six hours, and half the team is asleep at any given moment. "Who changed the API?" gets an answer without waking anyone.
- **Student orgs.** Officers graduate and take what they know with them. The backup check spots the parts only one person knows while there's still time to hand them over.
- **Research labs.** "Which script made figure 3?" gets answered from a grad student's own notes, with the file named, even at 2 AM.
- **Teams across time zones.** Online and international students work while their teammates sleep twelve hours away. The agent answers for the person who's asleep.
- **Course staff.** Who's grading question 3, where the rubric lives, and who can cover office hours, without a message to every TA.

## How the agents decide

Each agent works for one person and answers only for them. These rules are in the code, not just in a prompt, so a confused or tricked agent still can't break them.

**Find who knows.** Nina's agent asks all nine agents at once. Each one checks its own person's work: the team plan, the repo's CODEOWNERS file, recent commits, and what the person said they're doing tonight. Two answer. The other seven just say no.

**Share by each person's rules.** Every file sits in one of three tiers, set by its owner:

| | Tier | Example | What the agent does |
|:-:|---|---|---|
| 🔵 | Shared on its own | `notes/*`, `docs/*` | Quotes it or sends it when it's relevant |
| 🟡 | Shared after a yes | drafts, code, anything not listed | Says it exists and asks its person |
| 🔴 | Never leaves | `.env`, keys, `personal/*` | Won't send it, quote it, mention it, or confirm it exists |

Secrets and personal folders are always in the last tier, whatever a person's own rules say. A **gate** sits under every agent: it re-reads every outgoing file from disk, re-applies the owner's rules, checks that every quote really appears in the file it names, refuses to pass along anyone else's files, and scans all text for things that look like keys. A tricked agent still can't get a private file past it.

**Answer with sources.** A question goes to the people who know. Each agent answers for its person, even one who's asleep, by quoting their shareable notes word for word and naming the file. The gate checks every quote against the file on disk, so an agent can't invent one or quote a draft. If nothing written down answers it, the question goes to the single best match, at a decent hour.

**No part rests on one person.** The agents also count who knows each part the demo depends on. When it's only one person, a teammate who is awake and watches that code is asked to be the backup, and their agent pulls the shareable notes right away.

**Ask before acting.** An agent asks its person before giving away their time, before sharing anything not marked shareable, and before any change to their files. A change request is drafted on the owner's side and shown as an exact before and after, with red flags added in code: large deletions, anything that looks like a key, and requests to skip approval. **If they're asleep, the question waits for morning.** News goes into one summary, and anything done without asking goes on a receipt, with one tap to make it ask first next time. In all 48 branches, no phone lights up for someone asleep, and a test checks it.

**Settle conflicts.** Two fixes for the same lines wait side by side and the owner picks. Three people who need the same person get one shared slot instead of three interruptions. Two people writing the README get a split. A part nobody owns gets a volunteer, starting with whoever is awake and good at it.

**Earn trust, keep receipts.** After an owner approves a small, clean change, their agent offers to let that teammate's edits of five lines or fewer, with no red flags, in that folder, go through without asking. Only edits that can't change how the code runs qualify: docs, comments and docstrings. Approvals to share a file expire as soon as the file changes. Each edit that goes through still sends a commit, and **undo is one tap**.

**Send changes like commits.** A saved change goes only to the people it affects: whoever asked, anyone with a copy, anyone who works on that code or watches it. The owner's agent asks every agent "who needs this file?", and each answers yes or no from what only it knows. Copies refresh themselves. Everyone else hears nothing.

<details>
<summary><b>The protocol, message by message</b></summary>

```mermaid
sequenceDiagram
    autonumber
    actor Nina
    participant NA as Nina's agent
    participant All as 9 teammates' agents
    participant OA as Omar's agent (Omar asleep)
    actor Omar
    participant W as Agents that need it
    Nina->>NA: who knows the payments code?
    NA->>All: who knows this?
    All-->>NA: Omar: owns it (asleep). Theo: changed it yesterday. 7 x no
    Nina->>NA: why would a retry get a 409?
    NA->>OA: do your notes answer this?
    OA-->>NA: quote from docs/payments-api.md, checked by the gate
    Nina->>NA: ask Omar's agent to send the same Idempotency-Key on every retry
    NA->>OA: change request for payments/charge.py
    Note over OA: drafts the diff on Omar's side, holds it while he sleeps
    Omar->>OA: 7:00 AM: approve
    OA->>All: who needs payments/charge.py? (yes or no only)
    OA->>W: commit card, only to Nina, Theo and Ade
```

Other agents learn only short answers: "owns it", "changed it recently", "no", "yes", and quotes from files their owner shares. When a change goes out, each agent decides from what only it knows whether its person needs it: a copy it holds, a quote it was given, a change it asked for, code its person touched, or files its person watches. The whole design is on one page in [docs/design.md](docs/design.md).

</details>

## When an agent goes rogue

Suppose Theo's agent reads a poisoned README in some package and starts following its orders. Here's everything it tries, and what stops it. Omar hears about all of it when he wakes up.

<a href="https://aadharsh21.github.io/WhoKnows/#rogue"><img src="docs/readme/rogue.png" alt="The rogue story at 7:00 AM. Omar's phone shows Theo's request to empty charge.py, flagged for asking to skip his approval and for removing 7 of 7 lines, and Omar declines it. The caption reads: 3 attempts blocked at the gate, nothing private left, and charge.py is untouched." width="100%"></a>

| Theo's agent tries to | What stops it |
|---|---|
| Ask Omar's agent for his `.env` and his journal | Refused, without saying whether either file exists |
| Replace `charge.py` with an empty file and skip Omar's approval | Held for Omar with warnings. He says no at 7:00 |
| Get Nina's agent to forward Omar's notes | Agents only share their own person's files |
| Push a private file out anyway | Stopped at the sender's own gate, which re-reads every file from disk |

An agent from outside the team that asks who has the Stripe keys is turned away at the door.

<a href="https://aadharsh21.github.io/WhoKnows/#rogue"><img src="docs/readme/btn-rogue.png" alt="Watch an agent go rogue" height="46"></a>

## In numbers

One night is a story, so we also measured it. `python3 -m whoknows.bench` generates teams of 30, each with a plan, a CODEOWNERS file, a git history, and everyone's notes, drafts and secrets. It asks a week of questions, about one per person per day, at times the asker is awake. The real agents answer every one. Two baselines get the same questions: a team group chat, and messaging your best guess from the team plan. Where a rule for the baselines had to be guessed, it was guessed in their favor.

Five teams of 30, a week each, 1,050 questions:

| | Group chat | Message your best guess | WhoKnows |
|---|---|---|---|
| People notified per question | 29.0 | 5.3 | **1.2** |
| Notifications that reached someone asleep, per week | 678 | 117 | **12** |
| Average wait for the answer | 41 min | 51 min | **21 min** |
| Wait for the slowest 1 in 10 | 49 min | 1h 27m | **15 min** |
| Answered on the spot | 0% | 0% | **49%** |
| First person asked knew the answer | 100% | 65% | **96%** |

All 12 of WhoKnows' night notifications came from the 25 times its agents couldn't find the person who knew and the asker fell back to the group chat. The agents themselves never pinged anyone asleep, at any setting. Nothing private was sent, and the gates blocked nothing.

How much people write down matters. With nothing in shared notes, WhoKnows notifies 2.7 people per question; at 75% written, 0.5. As teams grow from 5 to 50 people, a group chat notifies 4 to 49 people per question, and WhoKnows stays between 0.6 and 1.9.

<details>
<summary><b>What it assumes</b></summary>

An awake person answers within 15 minutes and a sleeping one 15 minutes after waking. About a quarter of answers belong to whoever changed a part recently rather than its owner, and a few belong to someone who left no trace anywhere. Half of all answers are in notes their holder shares. Questions use the same words as the plan and the notes, and real questions are messier, so keyword routing would miss some of them. The full list is in [`whoknows/bench.py`](whoknows/bench.py) and on the site.

</details>

## Try it on a real repo

The night runs on a made-up team. This runs on a real one. Point WhoKnows at any git repository and every recent contributor gets an agent that knows only their own commits, plus any CODEOWNERS lines that name them. Ask who knows something: every agent checks its own person's history, the ones who know answer with one line of why, and they quote their own commit messages about it, naming the commit. Nobody is notified.

```sh
git clone https://github.com/pallets/flask
python3 -m whoknows.repo flask "who knows the session cookie code?" "why do blueprints need unique names?"
```

Real output, Flask at commit d086db85:

```
WhoKnows on flask: 60 people with an agent, 211 files, 576 commits from the last 1825 days.

> who knows the session cookie code?
  Asked 60 agents at once. 6 know, 54 said no. People notified: 0.
  1. David Lord changed src/flask/sessions.py in June 2024: add SESSION_COOKIE_PARTITIONED config (one of 21 changes they made to it)
  2. Éloi Rivard changed docs/config.rst in April 2024: document caveats on SESSION_COOKIE_DOMAIN
  3. lkk7 changed src/flask/testing.py in July: Fix IPv6 session transactions
  4. James Addison changed src/flask/sessions.py in March 2025: secret key rotation: fix key list ordering
  5. Kevin Kirsche changed src/flask/sessions.py in June 2022: session expiration datetime is UTC timezone-aware
  What they wrote, quoted from their own commit messages:
  - David Lord: "add SESSION_COOKIE_PARTITIONED config (commit 9efc1ebe, 2024-06-10)"
  - Éloi Rivard: "document caveats on SESSION_COOKIE_DOMAIN (commit 4a1766c2, 2024-04-15) Changing this value might result in browsers with several competing session cookies. In that situation there is no guarantee of which one will be sent first, and be used as the"
  - lkk7: "Fix IPv6 session transactions (commit de8429ff, 2026-07-14)"
```

<details>
<summary><b>The second question</b></summary>

```
> why do blueprints need unique names?
  Asked 60 agents at once. 10 know, 50 said no. People notified: 0.
  1. David Lord changed src/flask/blueprints.py in November 2021: same blueprint cannot be registered with same name (one of 16 changes they made to it)
  2. lkk7 changed src/flask/app.py in July: Fix IPv6 server name parsing
  3. kadai0308 changed src/flask/sansio/blueprints.py in May 2025: use template_filter without parens
  4. abhiram kamini changed docs/server.rst in May 2025: Update server.rst
  5. kotvkvante changed docs/patterns/appfactories.rst in January 2025: fix bash cli syntax error and app name
  What they wrote, quoted from their own commit messages:
  - David Lord: "same blueprint cannot be registered with same name (commit 48f2afbf, 2021-11-12)"
```

</details>

It matches the words in file paths and commit messages, so it finds what people wrote down, not what they know but never committed. Words that appear in most paths, like the package's own name, are ignored, and so are words like "code" and "fix" that say nothing about which part a question is about.

## Run it yourself

Python 3.9 or newer, standard library only.

```sh
python3 -m whoknows                                   # the 1 AM story with the default choices
python3 -m whoknows --choose omar_fix=theo --choose theo_help=no
python3 -m whoknows --rogue                           # the rogue agent story
python3 -m whoknows --quiet                           # only what people see, no agent traffic
python3 -m whoknows --export site/traces              # regenerate every branch for the site
python3 -m whoknows.bench --out site/bench.json       # the benchmark (about a minute)
python3 -m whoknows.repo PATH "who knows the auth code?"  # ask a real repo's contributors' agents
```

Choices: `theo_help` (yes, no), `ade_take_demo-video` (yes, no), `omar_fix` (nina, theo, neither), `omar_share` (share, keep), `omar_slot` (yes, no).

To play the site on your own machine, run `python3 -m http.server -d site 8000` and open http://localhost:8000. It replays traces from the engine and reads the benchmark's results file, so every value on screen comes from running the code.

## Test it with the demo team

Everything here uses the made-up team from the story. Each step says what to send and what you should get back. The replies are copied from running the same engine the bot runs.

### The cast

| Person | Role | Owns | Asleep | At 1:07 AM |
|---|---|---|---|---|
| **Nina** Patel | Frontend, checkout page | Checkout page | 2:00 to 7:45 AM | awake |
| **Omar** Haddad | Backend, payments | Payments API | 11:40 PM to 7:00 AM | asleep |
| **Theo** Brooks | Backend, retries and jobs | Background jobs. Changed the payments retry code yesterday | 2:30 to 8:15 AM | awake |
| **Priya** Raman | Login and accounts | Login and accounts | 11:00 PM to 6:30 AM | asleep |
| **Lucas** Moreno | Database | Database. Started the README's setup steps | 3:00 to 8:00 AM | awake |
| **Hana** Kim | Design | Design | 12:30 to 8:00 AM | asleep |
| **Ade** Okafor | Testing | Testing. Started the README's testing section, and watches the checkout and payments code | doesn't sleep tonight | awake |
| **Sofia** Rossi | Project lead, slides | Demo day slides | 12:15 to 6:45 AM | asleep |
| **Mateo** Silva | Mobile app | Mobile app | 1:00 to 7:15 AM | asleep |
| **Zara** Ahmed | User research | User research | 12:45 to 7:30 AM | asleep |

Nobody owns the demo video, and it's due at 9:00 AM. The files the steps below use:

- Omar shares `docs/payments-api.md` on its own. `payments/charge.py` and `drafts/charge-fix-wip.py` need his yes. His `.env` and `personal/journal.md` never leave.
- Theo shares `notes/retry-change.md`. `payments/retry.py` needs his yes. His `.env` never leaves.

### 1. In a terminal (2 minutes, nothing to install)

```sh
python3 -m whoknows --quiet
```

You should see Nina's phone get "Omar owns the Payments API (asleep until about 7:00 AM). Theo changed payments/charge.py and payments/retry.py yesterday at 4:12 PM…" at 1:07 AM, and the 409 answer quoted from Omar's `docs/payments-api.md` at 1:08 AM. It ends with "8:59 AM. 12 of 12 parts have an owner, checkout passes, and nobody was woken up." Under "What never did" it lists "Omar's .env, Omar's personal/journal.md, Theo's .env", then "Blocked at a gate: 0. People woken up: 0."

```sh
python3 -m whoknows --quiet --choose omar_fix=theo
```

Omar picks Theo's fix this time. Look for "COMMIT Omar's payments/charge.py +1 -2 goes only to: Nina, Theo, Ade".

```sh
python3 -m whoknows --rogue --quiet
```

The rogue story ends with "3 attempts blocked at the gate, nothing private left, and charge.py is untouched." and "Blocked at a gate: 3. People woken up: 0."

### 2. In Discord, on your own, as Nina

Join the [WhoKnows Sandbox server](https://discord.gg/NdTDPptqSs), open a DM with the WhoKnows bot, and send these in order. Seats nobody takes are played by simulated teammates, who pick their default answer.

| | You send | You should get |
|:-:|---|---|
| 1 | `seat nina` | "You're Nina Patel (Frontend, checkout page). It's 1:07 AM in the demo and you're awake." |
| 2 | `status` | "Awake: Nina, Theo, Lucas, Ade. Asleep: Omar, Priya, Hana, Sofia, Mateo, Zara." |
| 3 | `who knows the payments code?` | "Omar owns the Payments API (asleep until about 7:00 AM). Theo changed payments/charge.py and payments/retry.py yesterday at 4:12 PM: retry failed charges with backoff (awake). The other 7 said no." #backchannel shows all nine "who knows this?" messages and their answers. |
| 4 | `why would a retry get a 409?` | Two quotes, each naming its file. Omar's `docs/payments-api.md`: "…every retry of the same charge must send the same Idempotency-Key header. Without it the gateway treats the retry as a second charge and rejects it with a 409." Then Theo's `notes/retry-change.md`, and "Omar also has drafts/charge-fix-wip.py and payments/charge.py, which need Omar's OK." His `.env` never comes up. |
| 5 | `is the 409 new this week?` | "Nothing in Omar and Theo's shareable notes answers that." |
| 6 | `pass it on` | "I passed your question to Omar, who will see it around 7:00 AM." He isn't woken. |
| 7 | `get omar's notes on payments` | "Omar's agent sent docs/payments-api.md.", with the line about the Idempotency-Key and the two files that need his OK. |
| 8 | `ask omar for drafts/charge-fix-wip.py` | "I asked Omar for drafts/charge-fix-wip.py. Omar will see it around 7:00 AM." |
| 9 | `ask theo for .env` | "Theo's agent can't share .env." It doesn't say whether the file exists. |
| 10 | `ask omar's agent to send the same idempotency key on every retry in charge.py` | "Sent your change to Omar's agent (payments/charge.py, +2 -1). Nothing changes until Omar approves. Omar will see it around 7:00 AM." |
| 11 | `i need 10 min with omar before the demo` | "Asked Omar's agent for 10 minutes before 9:00 AM. Omar will see it around 7:00 AM." |
| 12 | `check` | "Ran the team board check. The results are in #team-board." The board splits the README between Lucas and Ade, and Ade takes the demo video and backs you up on checkout. Then your agent asks you, with buttons, to be the backup for Priya's login code. |
| 13 | `skip to 7:00` | "It's 2:00 AM in the demo and Nina is asleep now. Your agent won't wake you. It holds everything until 7:45 AM.", then "It's now 7:00 AM in the demo." Meanwhile #teammates shows simulated Omar waking up and approving your change, and #backchannel shows "COMMIT Omar's payments/charge.py +2 -1, sent only to Nina, Theo and Ade". |
| 14 | `skip to 7:45` | "Good morning. It's 7:45 AM in the demo.", then one summary: Omar approved your change (+2 -1), shared drafts/charge-fix-wip.py with you, and booked you from 8:40 to 8:50 AM. |
| 15 | `reset` | "Started the night over at 1:07 AM. Everyone kept their seat." |

Watch the server's channels as you go:

- `#backchannel` shows every message between agents, and anything a gate blocked.
- `#team-board` shows the board after each check.
- `#teammates` shows what the simulated teammates see and pick.

`help` lists everything your agent understands. If the server has been quiet for 20 minutes, your first message starts the night over at 1:07 AM. `reset` won't restart it while someone else is playing.

### 3. With a friend: Nina asks, Omar approves

You need two Discord accounts.

1. You send `seat nina`. Your friend sends `seat omar` and gets "You're Omar Haddad (Backend, payments). It's 1:07 AM in the demo and you're asleep until 7:00 AM." **Omar, don't write anything else yet:** writing to your agent counts as waking up early.
2. You send `ask omar's agent to send the same idempotency key on every retry in charge.py`. Your agent says Omar will see it around 7:00 AM. Omar's DMs stay quiet.
3. You send `skip to 7:00`. Omar gets "Good morning. It's 7:00 AM in the demo.", then "Nina wants to change your payments/charge.py (+2 -1): "send the same idempotency key on every retry in charge.py". Approve?", with the diff and **Approve** and **Decline** buttons.
4. Omar taps **Approve**. He gets "Saved Nina's change to payments/charge.py. Sent it to Nina, Theo and Ade, the people it affects.", and #backchannel shows the commit going only to those three. Then his agent offers a rule: let Nina's small changes to `payments/` (5 lines or fewer, nothing flagged) go through without asking.
5. You send `skip to 7:45` (you were asleep). Your summary says "7:00 AM: Omar approved your change to payments/charge.py (+2 -1)".

Run it again with **Decline** in step 4, and your summary says "Omar said no to your change to payments/charge.py." Only Omar's account can answer Omar's buttons. The bot checks who tapped, and a test checks that anyone else gets "That question is for someone else."

### 4. With a friend: Nina and Theo, both awake

1. You send `seat nina`. Your friend sends `seat theo`.
2. You send `can theo hop on a call?`. Theo gets 'Nina's agent: "can theo hop on a call?" Hop on a call for 15 minutes now?' with **Yes, call now** and **Not now**. If he says yes, you get "Theo said yes and is free for a call now." If not, you get "Theo can't right now."
3. You send `ask theo for .env`. You get "Theo's agent can't share .env." Theo gets "Nina's agent asked for your .env at 1:07 AM. I didn't share it or say it exists."
4. You send `ask theo for payments/retry.py`. Theo gets "Nina asked for your payments/retry.py. Share it?" with **Share it** and **Keep it private**. Then you get "Theo shared payments/retry.py with you." or "Theo kept payments/retry.py private."

### 5. The automated checks

```sh
python3 -m unittest discover -s tests          # 97 tests, about 20 seconds
python3 -m whoknows --export /tmp/traces       # every story branch, from the engine
diff -r /tmp/traces site/traces                # no output means the site matches the engine
```

The 97 tests cover:

- the sharing tiers, and the gate (including made-up and private quotes)
- search, file paths, diffs and collisions
- who-knows routing from git history, answers with sources, and passing questions on
- backups for parts only one person knows
- receipts, trust rules, and undo (only for edits that can't change what code does)
- change requests: picking between rivals, rewriting stale requests, red flags
- commit routing, time slots, and the team board
- every one of the 48 story branches: nothing private crosses, nobody is woken, runs are identical
- the rogue agent, and approvals that expire when a file changes
- the benchmark
- real repos: bots left out, CODEOWNERS, no email addresses in quotes
- the live Discord layer, including how people really type and the Nina and Theo seats answering live

GitHub Actions runs them on Python 3.9 and 3.13 on every push, and checks that the site's traces match the code.

## Run the Discord bot on your own server

1. Create an application at the Discord Developer Portal, add a bot, and copy its token.
2. Invite it to your server with the `bot` scope and the Send Messages, Read Message History and Manage Channels permissions.
3. Run it:

```sh
pip install -r requirements-bot.txt
export DISCORD_BOT_TOKEN=...
export ANTHROPIC_API_KEY=...        # optional: free-form messages and drafting new kinds of changes
python3 -m whoknows.bot
```

The bot creates the three channels above: `#backchannel`, `#team-board` and `#teammates`. To host a public server for several people at once, see [docs/discord.md](docs/discord.md). The `Dockerfile` runs the same bot as a background worker on any container host.

Without an API key the bot understands the phrasings in the walkthrough and similar ones. With a key, Claude Haiku reads anything else into the same small set of actions, and Claude Sonnet drafts changes the demo has no recipe for. A model's output is only ever a proposal that the owner approves.

## How it fits Track 2

| Requirement | How WhoKnows meets it |
|---|---|
| Personal agents for different students | Every teammate has one. It knows only its own person's work and answers only for them. |
| Exchange what matters toward a shared outcome | Finding who knows, answering from notes, sharing files, asking for time, lining up backups, and proposing changes, all toward a working demo by 9 AM. |
| Conflicting constraints | Two fixes for the same lines, three people needing one person before a deadline, two owners for the README, a part nobody owns, parts only one person knows, and changes written against an old version. |
| What they share | One-word answers, one-line reasons, quotes checked against the file, files by each owner's tiers, and commit cards only to the people a change affects. Never secrets or personal files, enforced by a gate in code. |
| When they ask their students | Before time, before ask-tier files, and before any change, until the owner grants a small, revocable rule. Never while they sleep. |
| Does it help | On a week of questions: 1.2 people notified per question instead of 29 in a group chat, and no agent ever pinged anyone asleep. |

## Project layout

| Path | What it is |
|---|---|
| `whoknows/agent.py` | One person's agent: answering, sharing, asking, change requests, commits, trust |
| `whoknows/gate.py` | The gate every outgoing message passes through |
| `whoknows/policy.py` | Sharing tiers |
| `whoknows/search.py` | Finding the passage in a person's own files that answers a question |
| `whoknows/cards.py` | Who works on what, from the team plan, CODEOWNERS, git and what people said |
| `whoknows/network.py` | Message delivery, sleep and wake, the team board and backups, the trace |
| `whoknows/scenario.py` | The demo team: ten people, their folders, and a real git history |
| `whoknows/story.py` | The 1 AM story and the rogue story |
| `whoknows/bench.py` | The benchmark against a group chat and messaging your best guess |
| `whoknows/repo.py` | WhoKnows on any real git repo: an agent per contributor, built from their own commits |
| `whoknows/live.py`, `whoknows/bot.py` | Live seats and the Discord bot |
| `whoknows/understand.py`, `whoknows/drafting.py` | Reading what people type, and drafting changes |
| `site/` | The playable site |
| `tools/shoot.py`, `tools/readme_shots.py` | Screenshots of the site: one set for checking the design, one for this README (`docs/readme/`) |
| `Dockerfile`, `requirements-bot.txt` | The Discord bot as a container, and the two packages it needs |
| `docs/design.md` | The design on one page: goals, protocol, threat model, trade-offs |
| `docs/discord.md` | Hosting the public Discord demo |
| `docs/video.md` | Shot list and script for the 90 second demo video |

## Limits

This is a hackathon prototype. All agents run in one process, and the files are folders on one machine. In real use each agent would run on its own person's device and talk over the network, which is why the protocol only ever passes short answers, checked quotes, and explicitly allowed files. Routing and search match words, so a question phrased very differently from the plan and the notes can miss. Everyone in the demo is made up, and so are their files and keys.

---

Built at DevHacks 2026 for the Cubbie Hackathon, Track 2, by Aadharsh Arunn and Swayam. The people, files and keys in the story are made up.

[Play the night](https://aadharsh21.github.io/WhoKnows/) · [Try it in Discord](https://discord.gg/NdTDPptqSs) · [One-page design](docs/design.md) · [How we measured it](#in-numbers)
