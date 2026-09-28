"""Test core utility functions."""

import unittest

from qmi.core.util import check_value_structures_equal


class TestCheckValueStructuresEqual(unittest.TestCase):
    """Test structural value type checks."""

    def test_scalar_values(self) -> None:
        """Scalars only need to have the same type."""
        self.assertTrue(check_value_structures_equal(True, False))
        self.assertTrue(check_value_structures_equal("foo", "bar"))
        self.assertTrue(check_value_structures_equal(1.0, 2.0))
        self.assertTrue(check_value_structures_equal(1, 2))

        self.assertFalse(check_value_structures_equal(True, 1))
        self.assertFalse(check_value_structures_equal(1, 1.0))
        self.assertFalse(check_value_structures_equal("1", 1))

    def test_lists_and_tuples(self) -> None:
        """Sequences must match type, length and item structure."""
        self.assertTrue(check_value_structures_equal([1, "a", 1.0], [2, "b", 2.0]))
        self.assertTrue(check_value_structures_equal((1, ["a"]), (2, ["b"])))

        self.assertFalse(check_value_structures_equal([1, "a"], [2]))
        self.assertFalse(check_value_structures_equal([1, "a"], [2, 3]))
        self.assertFalse(check_value_structures_equal([1, "a"], (2, "b")))
        self.assertFalse(check_value_structures_equal((1, ["a"]), (2, ("b",))))

    def test_sets(self) -> None:
        """Sets must match type, length and item structure."""
        self.assertTrue(check_value_structures_equal({1, "a", 1.5}, {2, "b", 2.5}))
        self.assertTrue(check_value_structures_equal({(1, "a"), (2, "b")}, {(3, "c"), (4, "d")}))

        self.assertFalse(check_value_structures_equal({1, "a"}, {2}))
        self.assertFalse(check_value_structures_equal({1, "a"}, {2, 3}))
        self.assertFalse(check_value_structures_equal({(1, "a")}, {(2, 3)}))

    def test_dictionaries(self) -> None:
        """Dictionaries must match type, keys and value structure."""
        self.assertTrue(
            check_value_structures_equal(
                {"a": 1, "b": ["x", 2.0]},
                {"a": 2, "b": ["y", 3.0]}
            )
        )

        self.assertFalse(check_value_structures_equal({"a": 1}, {"b": 1}))
        self.assertFalse(check_value_structures_equal({"a": 1}, {"a": "1"}))
        self.assertFalse(check_value_structures_equal({"a": [1]}, {"a": (1,)}))


if __name__ == "__main__":
    unittest.main()
