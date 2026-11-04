import unittest

from sokoban import Game, Level


class GameTests(unittest.TestCase):
    def setUp(self):
        self.level = Level("Test", (
            "#######",
            "#     #",
            "#  .  #",
            "#  $  #",
            "#  @  #",
            "#######",
        ))
        self.game = Game(levels=(self.level,))

    def test_player_moves_into_empty_floor(self):
        self.assertTrue(self.game.move(1, 0))
        self.assertEqual(self.game.player, (4, 4))
        self.assertEqual(self.game.moves, 1)

    def test_wall_blocks_move_without_counting_move(self):
        self.assertFalse(self.game.move(0, 1))
        self.assertEqual(self.game.player, (3, 4))
        self.assertEqual(self.game.moves, 0)

    def test_push_box(self):
        self.assertTrue(self.game.move(0, -1))
        self.assertEqual(self.game.player, (3, 3))
        self.assertIn((3, 2), self.game.boxes)
        self.assertTrue(self.game.is_won)

    def test_box_cannot_be_pushed_into_wall(self):
        level = Level("Wall push", (
            "########",
            "#      #",
            "#  #$@##",
            "#   .  #",
            "########",
        ))
        game = Game(levels=(level,))
        self.assertFalse(game.move(-1, 0))
        self.assertIn((4, 2), game.boxes)

    def test_box_cannot_be_pushed_into_another_box(self):
        level = Level("Two boxes", (
            "########",
            "#      #",
            "#@$$.. #",
            "#      #",
            "########",
        ))
        game = Game(levels=(level,))
        self.assertFalse(game.move(1, 0))
        self.assertEqual(len(game.boxes), 2)

    def test_undo_restores_player_box_and_move_count(self):
        before_player = self.game.player
        before_boxes = set(self.game.boxes)
        self.game.move(0, -1)
        self.assertTrue(self.game.undo())
        self.assertEqual(self.game.player, before_player)
        self.assertEqual(self.game.boxes, before_boxes)
        self.assertEqual(self.game.moves, 0)

    def test_undo_returns_false_when_history_is_empty(self):
        self.assertFalse(self.game.undo())

    def test_restart_restores_initial_level_state(self):
        initial_player = self.game.player
        initial_boxes = set(self.game.boxes)
        self.game.move(1, 0)
        self.game.restart()
        self.assertEqual(self.game.player, initial_player)
        self.assertEqual(self.game.boxes, initial_boxes)
        self.assertEqual(self.game.moves, 0)

    def test_winning_state(self):
        self.assertTrue(self.game.move(0, -1))
        self.assertTrue(self.game.is_won)

    def test_next_level_resets_state(self):
        levels = (
            Level("One", ("#####", "#@$.#", "#####")),
            Level("Two", ("######", "#@ $.#", "######")),
        )
        game = Game(levels=levels)
        game.move(1, 0)
        self.assertTrue(game.next_level())
        self.assertEqual(game.level_index, 1)
        self.assertEqual(game.moves, 0)
        self.assertFalse(game.next_level())

    def test_level_requires_matching_box_and_goal_counts(self):
        with self.assertRaises(ValueError):
            Game(levels=(Level("Broken", ("#####", "#@$.#", "# $ #", "#####")),))


if __name__ == "__main__":
    unittest.main()
