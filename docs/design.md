# WhoKnows: design in one page

## Problem

On a team of ten or more, the expensive question is not the hard one. It's "who knows about X?" It goes to a group chat that buzzes everyone, often at night, or to a best guess who passes it on. Meanwhile the answer is often already written down in someone's notes, and a teammate's file needs a two-line fix its owner would approve in a second.

## Goals

1. Find the person who knows, without asking a human.
2. Answer from what people already wrote down, quoting it, without exposing anything they didn't mean to share.
3. Change a teammate's file only with their approval, and show the change only to the people it affects.
4. Never wake anyone. Questions wait for a decent hour; news waits for a morning summary.

Non-goals: a shared index of everyone's files, a chat replacement, agents that act on their own judgment where a person should decide.

## Shape

Every person has their own agent. Agents talk only to each other, over a `Network` that runs each message through the sender's `Gate` on the way out and the replier's gate on the way back. There is no central store. Each agent searches only its own person's folder.

```
person <-> their agent <-> gate <-> network <-> gate <-> teammate's agent <-> teammate
```

| Piece | File | Job |
|---|---|---|
| Card | `cards.py` | What a person works on, from the team plan, CODEOWNERS, `git log`, and what they told their agent. Stays with the agent; only one-line answers leave. |
| Policy | `policy.py` | Three tiers per file: share, ask first, never. Secrets, keys and `personal/` are always never, whatever the rules say. |
| Gate | `gate.py` | Re-reads every outgoing file from disk, re-applies the owner's rules, checks every quote is really in the file, and scans all text for things that look like keys. It doesn't trust the agent. |
| Search | `search.py` | Finds the paragraph in a person's own shareable files that best matches a question and returns it word for word, so the gate can verify it. |
| Agent | `agent.py` | Answers other agents, asks its person before anything that changes files or spends time, holds questions while its person sleeps. |
| Network | `network.py` | Delivery, the clock, the trace, and an on-demand team check (duplicates, orphans, bus factor). |

## Protocol

All messages are small JSON bodies. The main ones:

- `who_knows` goes to every agent. Each replies `owner`, `touched`, `claims`, or `no`, with one line of why. Nothing else about the person leaves.
- `question` goes to the people who know. Each agent quotes up to two passages from files its person shares. Files that need an OK are named, never quoted. `question` with `hand_over` puts the question in front of the person, now if awake, in the morning summary if not.
- `fetch` and `share_request` move whole files, under the same tiers.
- `change` asks the owner's agent to draft a change on the owner's side. It is only a proposal: it waits for the owner, with red flags for big deletions, anything that looks like a key, and requests to skip approval. Two proposals that touch the same lines are shown side by side. A proposal written against an old version is redrafted.
- `watch_check` and `commit`: after a change, the owner's agent asks every agent "does your person need this?" Each answers yes or no from its own reasons (has a copy, was quoted it, asked for it, watches that path, changed that code). Only the yeses get the commit card.
- `time` and `slot`: requests for someone's time merge into one booking.

## Trust that grows

Agents earn autonomy the way people do. After an owner approves a small, clean change from a teammate, the agent offers a rule: let that teammate's changes of five lines or fewer, with no red flags, in that folder, go through without asking, as long as they can't change how code runs (docs, comments, docstrings; Python is compared by its syntax tree). Each one still sends a commit and asks "keep it?" with undo one tap away. Anything an agent does unasked while its person sleeps goes on a receipt they see when they wake, with a one-tap way to tighten the rules.

## Threat model

The agent itself might be fooled, for example by instructions planted in a README it read. So the safety rules live in the gate, which has no model and no judgment to fool. Tested attacks: asking for `.env` or a journal (refused without saying whether the file exists), forwarding someone else's file (agents only share their own person's files), a request to wipe a file and skip approval (held for the owner with warnings), a fooled agent sending a private file anyway (stopped at its own gate), and an agent from outside the team (turned away). Secrets never appear in any trace; the tests check every branch.

## Decisions and alternatives

- **Federated, not indexed.** A shared index would answer faster but would copy everyone's files into one place. Here nothing leaves a person's folder unless their rules allow it, at the moment it's asked for.
- **Cards from real signals, not a model's guess.** Routing uses the plan, CODEOWNERS and git history, which are cheap, explainable, and verifiable. A language model is used only at the edges: understanding what a person types, and drafting a change on the owner's side.
- **Quotes, not summaries.** A quote can be checked against the file. A summary can't.
- **Proposals, not edits.** No agent writes to another person's files. It asks their agent, which drafts the change and waits for its own person.

## Evidence

`python3 -m whoknows.bench` generates five teams of 30 with a plan, a git history and notes, asks a week of questions, and runs the real agents against two baselines. People notified per question: 29 in a group chat, 5.3 messaging your best guess, 1.2 with WhoKnows. Notifications reaching someone asleep per week: 678, 117, and 12, all 12 from the times WhoKnows fell back to the group chat. 91 tests run on Python 3.9 and 3.13 in CI. `python3 -m whoknows.repo` runs the same agents on any real git repo, one per contributor, built from their own commits.

## Limits

Questions in the benchmark use the same words as the plan and the notes; real questions are messier, and keyword routing will miss some. The benchmark's people answer within 15 minutes of seeing a message, which is a simplification. The demo runs all agents in one process; a real deployment would put each agent next to its person's files.
