"""Runner levels: per-level planning numbers, detection, layoff and promotion (TC-11, standard library only)."""
import copy
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from garmin_plan import levels, physiology, profile, templates  # noqa: E402

RULES = physiology.load_rules()
LEVELS = levels.load_levels()
TODAY = date(2024, 6, 5)
SECTIONS = ("volume", "split", "skeleton", "checks", "rotation")


class Params(unittest.TestCase):
    def test_every_level_resolves(self):
        for vol in templates.LEVELS:
            for qual in templates.LEVELS:
                with self.subTest(volume=vol, quality=qual):
                    r = levels.params(LEVELS, vol, qual, RULES)
                    self.assertEqual(r["rotation"]["level"], qual)
                    for sec in SECTIONS:
                        self.assertIsInstance(r[sec], dict)
                    self.assertIn("ramp", r["volume"])
                    self.assertIn("long_share_cap", r["split"])
                    self.assertIn("max_hard", r["checks"])

    def test_intermediate_is_the_old_rules(self):
        # the numbers rules.toml held before 08, now read from levels.toml at the intermediate level
        r = levels.params(LEVELS, "intermediate", "intermediate", RULES)
        v = r["volume"]
        self.assertEqual((v["ramp"], v["deload"], v["deload_every"], v["start_floor_km"], v["next_block_from_week"]),
                         (0.08, 0.85, 4, 10, 2))
        self.assertEqual(v["taper"], [0.7, 0.5])
        s = r["split"]
        self.assertEqual((s["long_share_cap"], s["long_over_longest_km"], s["long_time_cap_min"],
                          s["easy_min_km"], s["easy_min_min"]), (0.45, 2, 150, 5, 30))
        self.assertEqual((r["skeleton"]["f_min_days"], r["checks"]["max_hard"]), (4, 2))
        self.assertEqual((r["rotation"]["deload_lighter"], r["rotation"]["E"]), (1, "easy"))

    def test_overlay_leaves_other_sections_intact(self):
        before = copy.deepcopy(RULES)
        r = levels.params(LEVELS, "beginner", "advanced", RULES)
        self.assertEqual(RULES, before)                      # a copy: the shared rules never change
        for sec in ("paces", "bands", "phases", "caps", "fix", "feasibility"):
            self.assertEqual(r[sec], RULES[sec], sec)
        for phase in ("base", "rt", "it", "tm", "taper"):
            self.assertIn(phase, r["rotation"])

    def test_moved_numbers_left_rules_toml(self):
        self.assertNotIn("level", RULES["rotation"])
        self.assertNotIn("ramp", RULES["volume"])
        self.assertNotIn("long_share_cap", RULES.get("split", {}))
        self.assertNotIn("max_hard", RULES.get("checks", {}))

    def test_default_rules(self):
        self.assertEqual(levels.params(LEVELS, "novice", "novice"), levels.params(LEVELS, "novice", "novice", RULES))

    def test_unknown_level(self):
        with self.assertRaises(ValueError):
            levels.params(LEVELS, "elite", "novice", RULES)


class Overrides(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "profile.toml"
            p.write_text(text, encoding="utf-8")
            return profile.load_profile(p, [], [], TODAY)

    def test_set_in_profile(self):
        p = self.load('volume_level = "novice"\nquality_level = "Advanced"\n')
        self.assertEqual((p.volume_level, p.quality_level), ("novice", "advanced"))
        self.assertEqual((p.sources["volume_level"], p.sources["quality_level"]), ("set", "set"))

    def test_rejected(self):
        for text in ('volume_level = "elite"\n', "quality_level = 3\n", 'quality_level = ""\n'):
            with self.subTest(text=text), self.assertRaisesRegex(profile.ProfileError, "beginner, novice"):
                self.load(text)


if __name__ == "__main__":
    unittest.main()
