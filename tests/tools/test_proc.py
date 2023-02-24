import unittest

from qmi.tools.proc import is_local_host


class ProcTestCase(unittest.TestCase):
    
    def test_is_local_host(self):
        self.assertFalse(is_local_host("0.0.0.0"))
