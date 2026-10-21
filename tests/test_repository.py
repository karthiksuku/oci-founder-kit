"""Repository contract: the validator passes and catches the problems it claims to."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import validate  # noqa: E402


class Repository(unittest.TestCase):
    def test_validator_passes(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = validate.main()
        self.assertEqual(code, 0, buf.getvalue())

    def test_decide_track_skills_ship(self):
        names = {p.name for p in (ROOT / "skills").iterdir() if p.is_dir()}
        self.assertTrue({"founder-value", "founder-value-ai", "founder-value-brief",
                         "founder-value-economics", "founder-value-gtm"} <= names)


class FrontmatterParser(unittest.TestCase):
    def test_parses_nested_metadata(self):
        text = "---\nname: x\ndescription: d\nmetadata:\n  version: \"0.1.0\"\n---\nbody\n"
        meta, body = validate.parse_frontmatter(text)
        self.assertEqual(meta["metadata"]["version"], "0.1.0")
        self.assertEqual(body, "body\n")

    def test_rejects_missing_frontmatter(self):
        self.assertIsNone(validate.parse_frontmatter("# no frontmatter\n"))

    def test_accepts_crlf_and_closing_fence_at_end_of_file(self):
        self.assertEqual(validate.parse_frontmatter("---\r\nname: x\r\n---\r\nbody\r\n")[0]["name"], "x")
        self.assertEqual(validate.parse_frontmatter("---\nname: x\n---")[0]["name"], "x")


class SkillCheck(unittest.TestCase):
    def test_scalar_metadata_is_a_problem_not_a_crash(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "demo-skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: demo-skill\ndescription: d\nmetadata: foo\n---\nbody\n")
            problems = validate.check_skill(skill, root=Path(tmp))
        self.assertTrue(any("metadata" in p for p in problems))


class SecretPatterns(unittest.TestCase):
    def test_detects_private_key_header(self):
        header = "-----BEGIN " + "RSA PRIVATE KEY-----"
        self.assertTrue(any(p.search(header) for p in validate.SECRET_RES))

    def test_ignores_part_numbers(self):
        self.assertFalse(any(p.search('"part_number": "B97384"') for p in validate.SECRET_RES))


if __name__ == "__main__":
    unittest.main()
