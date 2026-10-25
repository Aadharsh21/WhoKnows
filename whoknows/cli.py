"""Run a story in the terminal.

    python3 -m whoknows.cli                       # the 1 AM story with the default choices
    python3 -m whoknows.cli --choose omar_fix=theo --choose theo_help=no
    python3 -m whoknows.cli --rogue               # the rogue agent story
    python3 -m whoknows.cli --export site/traces  # write every branch for the site
"""

from __future__ import annotations

import argparse
import sys
import textwrap

from .story import MAIN_CHOICES, export, run


def _names(trace):
    return {p["id"]: p["first"] for p in trace["people"]} | {"board": "Board"}


def _wrap(text, indent):
    return textwrap.fill(text, width=100, initial_indent="", subsequent_indent=" " * indent)


def show(trace, quiet=False, out=sys.stdout) -> None:
    names = _names(trace)
    who = lambda pid: names.get(pid, pid)
    start = trace["steps"][0]["t"] if trace["steps"] else 0
    first = [s for s in trace["steps"] if s["type"] == "status" and s["t"] == start]
    if first:
        awake = ", ".join(who(s["person"]) for s in first if s["state"] == "awake")
        asleep = ", ".join(who(s["person"]) for s in first if s["state"] == "asleep")
        print(f"{first[0]['time']:>8}  Awake: {awake}. Asleep: {asleep}.", file=out)
    for s in trace["steps"]:
        t = f"{s['time']:>8}  "
        kind = s["type"]
        if kind == "caption":
            print("\n" + _wrap(f"== {s['text']}", 3), file=out)
        elif kind == "status":
            if s["t"] != start:
                print(f"{t}{who(s['person'])} is {'awake' if s['state'] == 'awake' else 'asleep'}", file=out)
        elif kind == "phone":
            if s["sender"] == "person":
                line = f"{t}{who(s['person'])} types: {s['text']}"
            else:
                line = f"{t}{who(s['person'])}'s phone: {s['text']}"
            for i, part in enumerate(line.split("\n")):
                print(_wrap(part if i == 0 else f"{' ' * 12}{part}", 12), file=out)
        elif kind == "decision":
            chosen = next(o["label"] for o in s["options"] if o["value"] == s["chosen"])
            print(_wrap(f"{t}{who(s['person'])} is asked: {s['prompt']}", 12), file=out)
            print(f"{' ' * 10}  -> {who(s['person'])} picks \"{chosen}\"", file=out)
        elif kind == "msg":
            if not quiet:
                files = f"  [{', '.join(s['files'])}]" if s.get("files") else ""
                print(f"{t}    {who(s['sender'])} > {who(s['to'])}: {s['label']}{files}", file=out)
        elif kind == "blocked":
            print(f"{t}    BLOCKED {who(s['sender'])} > {who(s['to'])}: {s['label']} ({s['reason']})", file=out)
        elif kind == "commit":
            c = s["card"]
            to = ", ".join(who(p) for p in s["to"]) or "nobody"
            print(f"{t}COMMIT {who(c['owner'])}'s {c['path']} +{c['added']} -{c['removed']} goes only to: {to}",
                  file=out)
        elif kind == "board":
            if s.get("final") or not quiet:
                rows = [f"{p['name']}: {', '.join(who(o) for o in p['owners']) or 'NOBODY'}"
                        + (f" ({p['note']})" if p["note"] else "") for p in s["parts"]]
                flags = []
                if s.get("duplicates"):
                    flags.append("two people on: " + ", ".join(s["duplicates"]))
                if s.get("orphans"):
                    flags.append("nobody on: " + ", ".join(s["orphans"]))
                print(f"{t}BOARD " + "; ".join(rows) + (f"  << {'; '.join(flags)}" if flags else ""), file=out)
    summary = trace["summary"]
    print("\n== What crossed", file=out)
    print(f"   {summary['messages']} messages between agents. Requests: "
          + ", ".join(f"{k} {v}" for k, v in sorted(summary["requests"].items())), file=out)
    print("   Files shared: " + (", ".join(f"{who(f['owner'])}'s {f['path']}" for f in summary["files_crossed"])
                                  or "none"), file=out)
    print("== What never did", file=out)
    print("   " + ", ".join(f"{who(f['person'])}'s {f['path']}" for f in summary["never_left"]), file=out)
    print(f"   Blocked at a gate: {len(summary['blocked'])}. People woken up: {summary['woken_up']}.", file=out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run a WhoKnows demo story.")
    parser.add_argument("--rogue", action="store_true", help="run the rogue agent story")
    parser.add_argument("--choose", action="append", default=[], metavar="KEY=VALUE",
                        help="make a choice, e.g. omar_fix=theo. Keys: "
                             + ", ".join(f"{k} ({'/'.join(v)})" for k, v in MAIN_CHOICES))
    parser.add_argument("--quiet", action="store_true", help="hide agent-to-agent traffic")
    parser.add_argument("--export", metavar="DIR", help="write every branch as JSON for the site")
    args = parser.parse_args(argv)
    if args.export:
        index = export(args.export)
        print(f"Wrote {len(index['main'])} branches of the main story and the rogue story to {args.export}")
        return 0
    choices = dict(item.split("=", 1) for item in args.choose)
    show(run("rogue" if args.rogue else "main", choices), quiet=args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
