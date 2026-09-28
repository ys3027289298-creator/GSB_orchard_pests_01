import json
import os
import random
import tempfile
import unittest

from orchard.core import (
    BASE_YIELD,
    SPRAY_COST,
    OrchardGame,
    Tree,
    CommandError,
    current_yield,
)
from orchard import cli


class NormalDayTests(unittest.TestCase):
    def test_full_normal_day(self):
        game = OrchardGame()
        apple = game.plant("apple")
        pear = game.plant("pear")
        game.water(apple.id)
        game.water(pear.id)
        self.assertEqual(game.harvest(apple.id), BASE_YIELD["apple"] + 2)
        self.assertEqual(game.harvest(pear.id), BASE_YIELD["pear"] + 2)

        coins_before = game.coins
        earned = game.sell("apple", 5)
        self.assertEqual(earned, 5 * 3)
        self.assertEqual(game.coins, coins_before + earned)
        self.assertEqual(game.warehouse["apple"], BASE_YIELD["apple"] + 2 - 5)

        event = game.settle("normal")
        self.assertEqual(event, "normal")
        self.assertTrue(game.settled)
        game.advance_day()
        self.assertEqual(game.day, 2)
        self.assertFalse(game.settled)
        for tree in game.trees:
            self.assertFalse(tree.watered)
            self.assertEqual(tree.harvests_today, 0)


class RainDayTests(unittest.TestCase):
    def test_rain_clears_watered_flag(self):
        game = OrchardGame()
        tree = game.plant("apple")
        game.water(tree.id)
        self.assertTrue(tree.watered)
        game.settle("rain")
        self.assertFalse(tree.watered, "watered state must reset after rain")
        game.advance_day()
        self.assertTrue(game.water(tree.id).watered)  # watering works again

    def test_rain_skips_chopped_trees(self):
        game = OrchardGame()
        stump = game.plant("apple")
        game.chop(stump.id)
        game.settle("rain")
        self.assertFalse(stump.watered)


class PestDayTests(unittest.TestCase):
    def test_chopped_trees_not_infested(self):
        game = OrchardGame()
        stump = game.plant("apple")
        living = game.plant("pear")
        game.chop(stump.id)
        game.settle("pest")
        self.assertFalse(stump.pests, "chopped trees cannot get pests")
        self.assertTrue(living.pests)

    def test_spray_protects_trees(self):
        game = OrchardGame()
        tree = game.plant("apple")
        game.spray()
        game.settle("pest")
        self.assertFalse(tree.pests)
        self.assertEqual(current_yield(tree), BASE_YIELD["apple"])

    def test_unsprayed_pests_halve_yield(self):
        game = OrchardGame()
        tree = game.plant("pear")
        game.settle("pest")
        self.assertEqual(current_yield(tree), int(BASE_YIELD["pear"] * 0.5))


class SprayCostTests(unittest.TestCase):
    def test_spray_charged_per_tree_not_per_species(self):
        game = OrchardGame(coins=50)
        for _ in range(3):
            game.plant("apple")
        game.plant("pear")
        expected = 3 * SPRAY_COST["apple"] + SPRAY_COST["pear"]
        before = game.coins
        cost = game.spray()
        self.assertEqual(cost, expected)
        self.assertEqual(game.coins, before - expected)

    def test_spray_ignores_chopped_trees(self):
        game = OrchardGame(coins=50)
        stump = game.plant("apple")
        living = game.plant("apple")
        game.chop(stump.id)
        self.assertEqual(game.spray(), SPRAY_COST["apple"])
        self.assertFalse(stump.sprayed)

    def test_spray_unaffordable_changes_nothing(self):
        game = OrchardGame(coins=1)
        tree = game.plant("peach")
        with self.assertRaises(CommandError):
            game.spray()
        self.assertEqual(game.coins, 1)
        self.assertFalse(tree.sprayed)


class HarvestTests(unittest.TestCase):
    def test_harvest_uses_fresh_yield(self):
        game = OrchardGame()
        tree = game.plant("apple")
        game.settle("pest")
        self.assertEqual(current_yield(tree), 5)
        game.advance_day()
        game.spray()
        game.water(tree.id)
        self.assertEqual(game.harvest(tree.id), BASE_YIELD["apple"] + 2)

    def test_harvest_once_per_day(self):
        game = OrchardGame()
        tree = game.plant("apple")
        game.harvest(tree.id)
        with self.assertRaises(CommandError):
            game.harvest(tree.id)
        self.assertEqual(game.warehouse["apple"], BASE_YIELD["apple"])

    def test_chopped_tree_yields_nothing(self):
        tree = Tree(id=1, species="apple", watered=True, pests=True)
        tree.chopped = True
        self.assertEqual(current_yield(tree), 0)


class WarehouseTests(unittest.TestCase):
    def test_full_warehouse_rejects_fruit(self):
        game = OrchardGame(capacity=100)
        for _ in range(10):
            game.plant("apple")
        for tree in game.trees:
            game.harvest(tree.id)
        self.assertEqual(game.warehouse_used, 100)

        extra = game.plant("apple")
        with self.assertRaises(CommandError):
            game.harvest(extra.id)
        self.assertEqual(game.warehouse_used, 100, "failed harvest stores nothing")
        self.assertEqual(extra.harvests_today, 0)

    def test_capacity_boundary_exactly_fits(self):
        game = OrchardGame(capacity=10)
        tree = game.plant("apple")
        self.assertEqual(game.harvest(tree.id), 10)
        self.assertEqual(game.warehouse_used, 10)

    def test_partial_fruit_does_not_sneak_in(self):
        game = OrchardGame(capacity=11)
        first = game.plant("peach")  # base yield 6
        game.harvest(first.id)
        tree = game.plant("apple")  # yield 10, only 5 slots free
        with self.assertRaises(CommandError):
            game.harvest(tree.id)
        self.assertEqual(game.warehouse["apple"], 0)
        self.assertEqual(game.warehouse_used, 6)


class SellTests(unittest.TestCase):
    def test_failed_sale_keeps_fruit_and_coins(self):
        game = OrchardGame(coins=10)
        tree = game.plant("apple")
        game.harvest(tree.id)
        with self.assertRaises(CommandError):
            game.sell("apple", BASE_YIELD["apple"] + 1)
        self.assertEqual(game.warehouse["apple"], BASE_YIELD["apple"])
        self.assertEqual(game.coins, 10)

    def test_non_positive_amount_rejected(self):
        game = OrchardGame()
        game.plant("apple")
        for amount in (0, -3):
            with self.assertRaises(CommandError):
                game.sell("apple", amount)

    def test_sell_unknown_species_rejected(self):
        game = OrchardGame()
        with self.assertRaises(CommandError):
            game.sell("banana", 1)


class EventTests(unittest.TestCase):
    def test_same_event_never_triggers_twice_in_a_row(self):
        game = OrchardGame()
        game.rng = random.Random(1234)
        previous = None
        for _ in range(40):
            event = game.settle()
            self.assertNotEqual(event, previous)
            previous = event
            game.advance_day()

    def test_explicit_event_validated(self):
        game = OrchardGame()
        with self.assertRaises(CommandError):
            game.settle("earthquake")


class SettlementLockTests(unittest.TestCase):
    def test_no_actions_after_settlement(self):
        game = OrchardGame()
        tree = game.plant("apple")
        game.settle("normal")
        for action in (
            lambda: game.plant("apple"),
            lambda: game.chop(tree.id),
            lambda: game.water(tree.id),
            lambda: game.spray(),
            lambda: game.harvest(tree.id),
            lambda: game.sell("apple", 1),
            lambda: game.settle(),
        ):
            with self.assertRaises(CommandError):
                action()

    def test_actions_resume_next_day(self):
        game = OrchardGame()
        tree = game.plant("apple")
        game.harvest(tree.id)
        game.settle("normal")
        game.advance_day()
        new_tree = game.plant("pear")
        self.assertEqual(game.harvest(new_tree.id), BASE_YIELD["pear"])


class SaveLoadTests(unittest.TestCase):
    def roundtrip(self, game):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "save.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(game.to_dict(), handle)
            with open(path, "r", encoding="utf-8") as handle:
                return OrchardGame.from_dict(json.load(handle))

    def test_save_load_preserves_state(self):
        game = OrchardGame(coins=77, capacity=50)
        apple = game.plant("apple")
        pear = game.plant("pear")
        game.water(apple.id)
        game.harvest(pear.id)
        game.settle("pest")
        loaded = self.roundtrip(game)
        self.assertEqual(loaded.coins, 77)
        self.assertEqual(loaded.capacity, 50)
        self.assertEqual(loaded.day, 1)
        self.assertTrue(loaded.settled)
        self.assertEqual(loaded.last_event, "pest")
        self.assertEqual(len(loaded.trees), 2)
        self.assertTrue(loaded.trees[0].watered)
        self.assertTrue(loaded.trees[1].pests)
        self.assertEqual(loaded.warehouse["pear"], BASE_YIELD["pear"])

    def test_loaded_settled_day_still_locked(self):
        game = OrchardGame()
        game.plant("apple")
        game.settle("rain")
        loaded = self.roundtrip(game)
        with self.assertRaises(CommandError):
            loaded.plant("pear")

    def test_rng_state_roundtrips(self):
        game = OrchardGame()
        game.rng = random.Random(2026)
        game.settle()
        loaded = self.roundtrip(game)
        self.assertEqual(loaded.rng.getstate()[1], game.rng.getstate()[1])

    def test_empty_or_broken_save_rejected(self):
        for payload in (None, {}, {"coins": 1}, {"coins": "x", "capacity": 1,
                                                 "day": 1}, "nope"):
            with self.assertRaises(ValueError):
                OrchardGame.from_dict(payload)

    def test_overfull_warehouse_save_rejected(self):
        with self.assertRaises(ValueError):
            OrchardGame.from_dict({
                "coins": 0, "capacity": 5, "day": 1,
                "warehouse": {"apple": 6, "pear": 0, "peach": 0},
                "trees": [],
            })

    def test_cli_load_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.json")
            open(path, "w").close()
            with self.assertRaises(ValueError):
                cli.load_game(path)

    def test_cli_save_load_roundtrip(self):
        game = OrchardGame()
        game.plant("apple")
        game.plant("apple")
        game.spray()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "save.json")
            cli.save_game(game, path)
            loaded = cli.load_game(path)
        self.assertEqual(loaded.coins, game.coins)
        self.assertEqual(len(loaded.trees), 2)
        self.assertTrue(all(tree.sprayed for tree in loaded.trees))


class CliCommandTests(unittest.TestCase):
    def test_valid_commands(self):
        game = OrchardGame()
        self.assertIn("planted", cli.execute(game, ["plant", "apple"]))
        self.assertIn("watered", cli.execute(game, ["water", "1"]))
        self.assertIn("harvested", cli.execute(game, ["harvest", "1"]))
        self.assertIn("earned", cli.execute(game, ["sell", "apple", "3"]))
        self.assertIn("settled", cli.execute(game, ["settle"]))
        self.assertIn("begins", cli.execute(game, ["next"]))
        self.assertIn("day 2", cli.execute(game, ["status"]))

    def test_invalid_commands(self):
        game = OrchardGame()
        for args in (
            [],
            ["frobnicate"],
            ["plant"],
            ["plant", "apple", "pear"],
            ["plant", "banana"],
            ["water", "abc"],
            ["water", "99"],
            ["harvest", "1"],
            ["sell", "apple"],
            ["sell", "apple", "lots"],
            ["settle", "now"],
        ):
            with self.assertRaises(CommandError):
                cli.execute(game, args)

    def test_duplicate_inputs(self):
        game = OrchardGame()
        cli.execute(game, ["plant", "apple"])
        cli.execute(game, ["chop", "1"])
        cli.execute(game, ["chop", "1"])  # idempotent, no error
        self.assertTrue(game.trees[0].chopped)
        cli.execute(game, ["settle"])
        with self.assertRaises(CommandError):
            cli.execute(game, ["settle"])  # repeat not allowed
        cli.execute(game, ["next"])
        second = cli.execute(game, ["plant", "pear"])
        self.assertIn("#2", second)
        cli.execute(game, ["harvest", "2"])
        with self.assertRaises(CommandError):
            cli.execute(game, ["harvest", "2"])  # same day only once


if __name__ == "__main__":
    unittest.main()
