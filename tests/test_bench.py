import unittest

from whoknows import bench


class BenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = bench.run_teams(8, seeds=[1, 2])

    def test_agents_never_notify_anyone_asleep(self):
        arms = self.result["arms"]
        self.assertEqual(arms["whoknows"]["agent_night_pings"], 0)
        self.assertGreater(arms["group_chat"]["night_pings"], arms["whoknows"]["night_pings"])

    def test_nothing_private_crosses_and_nothing_is_blocked(self):
        w = self.result["arms"]["whoknows"]
        self.assertEqual(w["private_files_sent"], 0)
        self.assertEqual(w["blocked"], 0)

    def test_a_group_chat_notifies_everyone_and_whoknows_far_fewer(self):
        arms = self.result["arms"]
        self.assertEqual(arms["group_chat"]["notified_per_question"], 7)
        self.assertLess(arms["whoknows"]["notified_per_question"], arms["best_guess"]["notified_per_question"])

    def test_every_question_points_at_one_part_and_one_holder(self):
        team = bench.make_team(self._tmp(), 8, 3)
        self.assertTrue(all(f.holder for f in team.facts))
        self.assertEqual(len({f.question for f in team.facts}), len(team.facts))

    def _tmp(self):
        import tempfile
        from pathlib import Path
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        return Path(self._dir.name)


if __name__ == "__main__":
    unittest.main()
