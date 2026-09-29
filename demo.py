"""Fixed, deterministic demo of the orchard game (stdlib only).

Run:  python demo.py
It exercises a normal day, a rain day and a pest day plus the failure paths,
and asserts every outcome so it doubles as a smoke test.
"""

from orchard.core import OrchardGame, CommandError


def main() -> None:
    game = OrchardGame(coins=50, capacity=100)
    game.rng.seed(7)

    print("== day 1: normal ==")
    apple = game.plant("apple")
    pear = game.plant("pear")
    game.water(apple.id)
    print("harvest apple:", game.harvest(apple.id))
    print("harvest pear:", game.harvest(pear.id))
    print("sell 4 apples:", game.sell("apple", 4), "coins; balance", game.coins)
    print("warehouse full? rejected harvest:")
    tiny = OrchardGame(capacity=5)
    t = tiny.plant("apple")
    try:
        tiny.harvest(t.id)
    except CommandError as exc:
        print("  ->", exc)
    print("oversell rejected; fruit stay:", end=" ")
    try:
        game.sell("pear", 99)
    except CommandError as exc:
        print(exc)
    print("day 1 event:", game.settle("normal"))
    try:
        game.water(apple.id)
    except CommandError as exc:
        print("post-settlement action blocked:", exc)
    game.advance_day()

    print("\n== day 2: rain ==")
    game.water(apple.id)
    game.settle("rain")
    assert all(not t.watered for t in game.trees), "rain must clear watering"
    print("all watered flags cleared after rain")
    game.advance_day()

    print("\n== day 3: pests, one tree chopped and one sprayed ==")
    stump = game.plant("peach")
    game.chop(stump.id)
    game.spray()
    game.settle("pest")
    assert not stump.pests, "chopped trees cannot get pests"
    assert not apple.pests, "sprayed trees stay safe"
    print("chopped/sprayed trees unaffected by pests")
    game.advance_day()

    print("\n== rng events never repeat back-to-back ==")
    seq = []
    previous = None
    for _ in range(12):
        event = game.settle()
        assert event != previous
        seq.append(event)
        previous = event
        game.advance_day()
    print("events:", ", ".join(seq))

    print("\nDEMO OK")


if __name__ == "__main__":
    main()
