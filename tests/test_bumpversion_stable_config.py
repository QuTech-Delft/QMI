#! /usr/bin/env python3

"""Test the `.bumpversion_stable.toml` release configuration file.

This is a regression test for https://github.com/QuTech-Delft/QMI/issues/225, where the configuration used to
prepare a patch release of a stable branch failed to bump `CHANGELOG.md` and `CITATION.cff` correctly, and raised
an error while bumping `pyproject.toml`.
"""

import pathlib
import tomllib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BUMPVERSION_STABLE_TOML = REPO_ROOT / ".bumpversion_stable.toml"


class TestBumpversionStableConfig(unittest.TestCase):
    """Test the `[[tool.bumpversion.files]]` entries of `.bumpversion_stable.toml`."""

    def setUp(self):
        with open(BUMPVERSION_STABLE_TOML, "rb") as config_file:
            config = tomllib.load(config_file)
        self.files = config["tool"]["bumpversion"]["files"]

    def _get_entries(self, filename):
        return [entry for entry in self.files if entry["filename"] == filename]

    def test_changelog_search_pattern_is_literal_version_placeholder(self):
        # The patch release procedure (see RELEASE.md) prepares CHANGELOG.md with a literal
        # "## [VERSION] - Unreleased" header, not one containing the current version number. So the search
        # pattern must match that literal placeholder instead of "{current_version}".
        entries = self._get_entries("CHANGELOG.md")
        self.assertEqual(1, len(entries))
        self.assertEqual("[VERSION] - Unreleased", entries[0]["search"])
        self.assertEqual("[{new_version}] - Unreleased", entries[0]["replace"])

    def test_pyproject_toml_uses_plain_version_bump(self):
        # pyproject.toml should be bumped via a plain version string replacement, like in the other bumpversion
        # configuration files, instead of a "search"/"replace" pair that does not match any text in the file.
        entries = self._get_entries("pyproject.toml")
        self.assertEqual(1, len(entries))
        self.assertNotIn("search", entries[0])
        self.assertNotIn("replace", entries[0])

    def test_citation_cff_is_bumped(self):
        entries = self._get_entries("CITATION.cff")
        self.assertEqual(1, len(entries))
        self.assertEqual("v{current_version}", entries[0]["search"])
        self.assertEqual("v{new_version}", entries[0]["replace"])


if __name__ == "__main__":
    unittest.main()
