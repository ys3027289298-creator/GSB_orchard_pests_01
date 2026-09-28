"""Orchard management core.

Only the Python standard library is used.  The public API and the save format
(see ``OrchardGame.to_dict`` / ``OrchardGame.from_dict``) are stable; the CLI
in ``orchard.cli`` is a thin wrapper around the actions defined here.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

SPECIES = ("apple", "pear", "peach")

# Species -> base yield per harvest (fruit).
BASE_YIELD: Dict[str, int] = {"apple": 10, "pear": 8, "peach": 6}

# Species -> spray cost per living tree (coins).  Spraying is charged once per
# tree, never once per species.
SPRAY_COST: Dict[str, int] = {"apple": 2, "pear": 3, "peach": 4}

# Species -> coins earned per fruit sold.
FRUIT_PRICE: Dict[str, int] = {"apple": 3, "pear": 4, "peach": 5}

# Pest-stricken trees keep this fraction of their base yield.
PEST_YIELD_FACTOR = 0.5

EVENTS = ("normal", "rain", "pest")
SAVE_VERSION = 1


class CommandError(ValueError):
    """Raised for any invalid player command (unknown, bad argument, ...)."""


def _require_species(species: str) -> str:
    if not isinstance(species, str):
        raise CommandError("species must be a string")
    species = species.strip().lower()
    if species not in SPECIES:
        raise CommandError("unknown species: %r" % species)
    return species


@dataclass
class Tree:
    id: int
    species: str
    watered: bool = False
    sprayed: bool = False
    pests: bool = False
    chopped: bool = False
    harvests_today: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "species": self.species,
            "watered": self.watered,
            "sprayed": self.sprayed,
            "pests": self.pests,
            "chopped": self.chopped,
            "harvests_today": self.harvests_today,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Tree":
        try:
            tree = cls(
                id=int(data["id"]),
                species=_require_species(data["species"]),
            )
        except CommandError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid tree record: %s" % exc) from exc
        tree.watered = bool(data.get("watered", False))
        tree.sprayed = bool(data.get("sprayed", False))
        tree.pests = bool(data.get("pests", False))
        tree.chopped = bool(data.get("chopped", False))
        tree.harvests_today = int(data.get("harvests_today", 0))
        return tree


def current_yield(tree: Tree) -> int:
    """Harvest quantity for a tree *right now* (chopped trees yield nothing)."""

    if tree.chopped:
        return 0
    amount = BASE_YIELD[tree.species]
    # Watering must take effect the same day, including right before harvest.
    if tree.watered:
        amount += 2
    # Pests that were not sprayed away halve the yield.
    if tree.pests and not tree.sprayed:
        amount = int(amount * PEST_YIELD_FACTOR)
    return amount


@dataclass
class OrchardGame:
    coins: int = 50
    capacity: int = 100
    day: int = 1
    settled: bool = False
    trees: List[Tree] = field(default_factory=list)
    warehouse: Dict[str, int] = field(
        default_factory=lambda: {name: 0 for name in SPECIES}
    )
    last_event: Optional[str] = None
    event: Optional[str] = None
    rng: random.Random = field(default_factory=random.Random)
    _next_id: int = 1

    # ------------------------------------------------------------------ utils

    def _require_active_day(self) -> None:
        if self.settled:
            raise CommandError("day %d is already settled" % self.day)

    def get_tree(self, tree_id: int) -> Tree:
        for tree in self.trees:
            if tree.id == tree_id:
                return tree
        raise CommandError("no tree with id %d" % tree_id)

    @property
    def warehouse_used(self) -> int:
        return sum(self.warehouse.values())

    # ----------------------------------------------------------------- actions

    def plant(self, species: str) -> Tree:
        self._require_active_day()
        species = _require_species(species)
        tree = Tree(id=self._next_id, species=species)
        self._next_id += 1
        self.trees.append(tree)
        return tree

    def chop(self, tree_id: int) -> Tree:
        self._require_active_day()
        tree = self.get_tree(tree_id)
        # Chopping is idempotent: a chopped tree stays chopped, with no state.
        tree.chopped = True
        tree.watered = False
        tree.sprayed = False
        tree.pests = False
        return tree

    def water(self, tree_id: int) -> Tree:
        self._require_active_day()
        tree = self.get_tree(tree_id)
        if tree.chopped:
            raise CommandError("cannot water a chopped tree")
        tree.watered = True
        return tree

    def spray(self) -> int:
        """Spray every living tree; return coins spent (once per tree)."""

        self._require_active_day()
        living = [tree for tree in self.trees if not tree.chopped]
        cost = sum(SPRAY_COST[tree.species] for tree in living)
        if cost > self.coins:
            raise CommandError("spraying costs %d coins but only %d available"
                               % (cost, self.coins))
        self.coins -= cost
        for tree in living:
            tree.sprayed = True
            tree.pests = False
        return cost

    def harvest(self, tree_id: int) -> int:
        self._require_active_day()
        tree = self.get_tree(tree_id)
        if tree.chopped:
            raise CommandError("cannot harvest a chopped tree")
        if tree.harvests_today > 0:
            raise CommandError("tree %d already harvested today" % tree.id)
        amount = current_yield(tree)
        free = self.capacity - self.warehouse_used
        if amount > free:
            # Refuse instead of overflowing: nothing enters the warehouse.
            raise CommandError("warehouse full: %d fruit do not fit in %d slots"
                               % (amount, free))
        self.warehouse[tree.species] += amount
        tree.harvests_today += 1
        return amount

    def sell(self, species: str, amount: int) -> int:
        self._require_active_day()
        species = _require_species(species)
        try:
            amount = int(amount)
        except (TypeError, ValueError) as exc:
            raise CommandError("amount must be an integer") from exc
        if amount <= 0:
            raise CommandError("amount must be positive")
        available = self.warehouse[species]
        if amount > available:
            # Failed sale: fruit are never deducted and no coins change hands.
            raise CommandError("only %d %s fruit available" % (available, species))
        self.warehouse[species] = available - amount
        earned = amount * FRUIT_PRICE[species]
        self.coins += earned
        return earned

    # ------------------------------------------------------------------ events

    def roll_event(self) -> str:
        """Pick today's event; the same event never triggers twice in a row."""

        choices = [name for name in EVENTS if name != self.last_event]
        return self.rng.choice(choices)

    def apply_event(self, name: str) -> str:
        if name not in EVENTS:
            raise CommandError("unknown event: %r" % name)
        self.event = name
        self.last_event = name
        if name == "rain":
            # Rain waters every living tree and clears any manual watering
            # state at the same time (everyone ends the day un-watered).
            for tree in self.trees:
                if not tree.chopped:
                    tree.watered = False
        elif name == "pest":
            for tree in self.trees:
                # Chopped trees are gone: pests cannot touch them.
                if not tree.chopped and not tree.sprayed:
                    tree.pests = True
        return name

    def settle(self, event: Optional[str] = None) -> str:
        """End the current day and apply its weather/event exactly once."""

        if self.settled:
            raise CommandError("day %d is already settled" % self.day)
        name = event if event is not None else self.roll_event()
        self.apply_event(name)
        self.settled = True
        return name

    def advance_day(self) -> int:
        """Move to the next day (settles the current one if still open)."""

        if not self.settled:
            self.settle()
        self.day += 1
        self.settled = False
        for tree in self.trees:
            tree.watered = False
            tree.sprayed = False
            tree.pests = False
            tree.harvests_today = 0
        self.event = None
        return self.day

    # --------------------------------------------------------------- save/load

    def to_dict(self) -> dict:
        return {
            "version": SAVE_VERSION,
            "coins": self.coins,
            "capacity": self.capacity,
            "day": self.day,
            "settled": self.settled,
            "next_id": self._next_id,
            "last_event": self.last_event,
            "event": self.event,
            "rng_state": self.rng.getstate(),
            "warehouse": {name: self.warehouse.get(name, 0) for name in SPECIES},
            "trees": [tree.to_dict() for tree in self.trees],
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "OrchardGame":
        if not data:
            raise ValueError("save data is empty")
        if not isinstance(data, dict):
            raise ValueError("save data must be an object")
        try:
            game = cls(
                coins=int(data["coins"]),
                capacity=int(data["capacity"]),
                day=int(data["day"]),
            )
        except KeyError as exc:
            raise ValueError("missing save field: %s" % exc) from exc
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid save header: %s" % exc) from exc

        game.settled = bool(data.get("settled", False))
        game._next_id = int(data.get("next_id", 1))
        game.last_event = data.get("last_event")
        if game.last_event is not None and game.last_event not in EVENTS:
            raise ValueError("invalid last_event: %r" % game.last_event)
        game.event = data.get("event")
        if game.event is not None and game.event not in EVENTS:
            raise ValueError("invalid event: %r" % game.event)

        warehouse = data.get("warehouse", {})
        if not isinstance(warehouse, dict):
            raise ValueError("warehouse must be an object")
        total = 0
        for name in SPECIES:
            value = int(warehouse.get(name, 0))
            if value < 0:
                raise ValueError("negative warehouse count for %s" % name)
            game.warehouse[name] = value
            total += value
        if total > game.capacity:
            raise ValueError("warehouse contents exceed capacity")

        trees = data.get("trees", [])
        if not isinstance(trees, list):
            raise ValueError("trees must be a list")
        game.trees = [Tree.from_dict(item) for item in trees]

        rng_state = data.get("rng_state")
        if rng_state is not None:
            try:
                game.rng.setstate(tupleize(rng_state))
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid rng state: %s" % exc) from exc
        return game


def tupleize(value):
    """JSON arrays come back as lists; random.setstate wants nested tuples."""

    if isinstance(value, list):
        return tuple(tupleize(item) for item in value)
    return value
