#! /usr/bin/env python3

"""Test basic start/stop functionality of QMI framework.
"""

import unittest

import qmi
import qmi.core.context
import qmi.core.exceptions


class TestQmiBasic(unittest.TestCase):

    def test_start_stop(self):

        # Check qmi.context() throws QMI_NoActiveContextException if non-existing.
        with self.assertRaises(qmi.core.exceptions.QMI_NoActiveContextException):
            ctx = qmi.context()

        # Check qmi.info() works when there is no context.
        s = qmi.info()
        self.assertIsInstance(s, str)

        # Check qmi.stop() prohibited.
        with self.assertRaises(qmi.core.exceptions.QMI_NoActiveContextException):
            qmi.stop()

        # Start QMI.
        qmi.start("my_test_context")

        # Check qmi.context() returns a context.
        ctx = qmi.context()
        self.assertIsInstance(ctx, qmi.core.context.QMI_Context)
        self.assertEqual(ctx.name, "my_test_context")

        # Check qmi.info() works.
        s = qmi.info()
        self.assertIsInstance(s, str)

        # Check qmi.start() now prohibited.
        with self.assertRaises(qmi.core.exceptions.QMI_UsageException):
            qmi.start("my_second_context")

        # stop QMI
        qmi.stop()

        # Check qmi.context() returns None when there is no context.
        with self.assertRaises(qmi.core.exceptions.QMI_NoActiveContextException):
            ctx = qmi.context()

        # Check qmi.info() works when there is no context.
        s = qmi.info()
        self.assertIsInstance(s, str)

        # Check qmi.stop() now prohibited.
        with self.assertRaises(qmi.core.exceptions.QMI_NoActiveContextException):
            qmi.stop()
        

if __name__ == "__main__":
    unittest.main()
