import tempfile
import unittest
from pathlib import Path

from whoknows import clock, scenario
from whoknows.story import build_network


class TeamCase(unittest.TestCase):
    """A fresh copy of the demo team for each test, starting at 1:07 AM."""

    start = "01:07"
    choices: dict = {}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = scenario.build(Path(self._tmp.name))
        self.net = build_network(self.root, dict(self.choices))
        self.net.start(clock.parse(self.start))
        self.a = self.net.agents

    def tearDown(self):
        self._tmp.cleanup()

    def steps(self, step_type, **match):
        return [s for s in self.net.steps
                if s["type"] == step_type and all(s.get(k) == v for k, v in match.items())]

    def phone_texts(self, person):
        return [s["text"] for s in self.steps("phone", person=person, sender="agent")]
