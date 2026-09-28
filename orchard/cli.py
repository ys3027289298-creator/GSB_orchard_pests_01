"""Command line interface for the orchard game (stdlib only)."""

from __future__ import annotations

import json
from typing import List, Optional

from .core import CommandError, OrchardGame

SAVE_PATH = "save.json"

USAGE = (
    "commands: plant <species> | chop <id> | water <id> | spray | "
    "harvest <id> | sell <species> <amount> | settle | next | "
    "save [path] | load <path> | status | help | quit"
)


def _parse_int(text: str, what: str) -> int:
    try:
        return int(text)
    except (TypeError, ValueError) as exc:
        raise CommandError("%s must be an integer" % what) from exc


def execute(game: OrchardGame, args: List[str]) -> str:
    """Run one parsed command; return a human-readable result line."""

    if not args:
        raise CommandError("empty command")
    command = args[0].lower()

    if command == "help":
        return USAGE
    if command == "plant":
        if len(args) != 2:
            raise CommandError("usage: plant <species>")
        tree = game.plant(args[1])
        return "planted %s tree #%d" % (tree.species, tree.id)
    if command == "chop":
        if len(args) != 2:
            raise CommandError("usage: chop <id>")
        tree = game.chop(_parse_int(args[1], "tree id"))
        return "chopped tree #%d" % tree.id
    if command == "water":
        if len(args) != 2:
            raise CommandError("usage: water <id>")
        tree = game.water(_parse_int(args[1], "tree id"))
        return "watered tree #%d" % tree.id
    if command == "spray":
        if len(args) != 1:
            raise CommandError("usage: spray")
        cost = game.spray()
        return "sprayed living trees for %d coins" % cost
    if command == "harvest":
        if len(args) != 2:
            raise CommandError("usage: harvest <id>")
        amount = game.harvest(_parse_int(args[1], "tree id"))
        return "harvested %d fruit" % amount
    if command == "sell":
        if len(args) != 3:
            raise CommandError("usage: sell <species> <amount>")
        earned = game.sell(args[1], _parse_int(args[2], "amount"))
        return "earned %d coins" % earned
    if command == "settle":
        if len(args) != 1:
            raise CommandError("usage: settle")
        event = game.settle()
        return "day %d settled: %s" % (game.day, event)
    if command == "next":
        if len(args) != 1:
            raise CommandError("usage: next")
        day = game.advance_day()
        return "day %d begins" % day
    if command == "status":
        if len(args) != 1:
            raise CommandError("usage: status")
        return _status(game)
    raise CommandError("unknown command: %r" % command)


def _status(game: OrchardGame) -> str:
    trees = ", ".join(
        "#%d %s%s%s%s" % (
            tree.id,
            tree.species,
            " chopped" if tree.chopped else "",
            " pests" if tree.pests else "",
            " watered" if tree.watered else "",
        )
        for tree in game.trees
    ) or "none"
    stock = ", ".join("%s=%d" % (name, game.warehouse[name]) for name in game.warehouse)
    return ("day %d%s | coins %d | warehouse %d/%d (%s) | trees: %s"
            % (game.day, " settled" if game.settled else "", game.coins,
               game.warehouse_used, game.capacity, stock, trees))


def save_game(game: OrchardGame, path: str = SAVE_PATH) -> str:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(game.to_dict(), handle, ensure_ascii=False)
    return "saved to %s" % path


def load_game(path: str = SAVE_PATH) -> OrchardGame:
    with open(path, "r", encoding="utf-8") as handle:
        contents = handle.read()
    if not contents.strip():
        raise ValueError("save file is empty")
    return OrchardGame.from_dict(json.loads(contents))


def main(argv: Optional[List[str]] = None) -> int:
    game = OrchardGame()
    print(USAGE)
    while True:
        try:
            line = input("orchard> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        args = line.split()
        if args[0].lower() in ("quit", "exit"):
            return 0
        if args[0].lower() == "save":
            try:
                print(save_game(game, args[1] if len(args) > 1 else SAVE_PATH))
            except OSError as exc:
                print("error: %s" % exc)
            continue
        if args[0].lower() == "load":
            if len(args) != 2:
                print("error: usage: load <path>")
                continue
            try:
                game = load_game(args[1])
                print("loaded %s" % args[1])
            except (OSError, ValueError) as exc:
                print("error: %s" % exc)
            continue
        try:
            print(execute(game, args))
        except CommandError as exc:
            print("error: %s" % exc)


if __name__ == "__main__":
    raise SystemExit(main())
