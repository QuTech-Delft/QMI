import random
import unittest
import unittest.mock
import qmi
from qmi.core.transport import QMI_SerialTransport
from qmi.instruments.thorlabs import Thorlabs_Mpc320


class TestThorlabsMPC320(unittest.TestCase):
    def setUp(self):
        # Patch QMI context and make instrument
        self._ctx_qmi_id = f"test-tasks-{random.randint(0, 100)}"
        qmi.start(self._ctx_qmi_id)
        self._transport_mock = unittest.mock.MagicMock(spec=QMI_SerialTransport)
        with unittest.mock.patch(
            "qmi.instruments.thorlabs.mpc320.create_transport",
            return_value=self._transport_mock,
        ):
            self._instr: Thorlabs_Mpc320 = qmi.make_instrument(
                "test_mpc320", Thorlabs_Mpc320, "serial:transport_str"
            )
        self._instr.open()

    def tearDown(self):
        self._instr.close()
        qmi.stop()

    def test_get_idn_returns_identification_info(self):
        """Test get_idn method and returns identification info."""
        # Arrange
        expected_idn = ["Thorlabs", b"MPC320 ", 94000009, 3735810]
        # \x89\x53\x9a\x05 is 94000009
        # \x4d\x50\x43\x33\x32\x30\x0a is MPC320
        # x2c\x00 is Brushless DC controller card
        # \x02\x01\x39\x00 is 3735810
        self._transport_mock.read.side_effect = [
            b"\x06\x00\x54\x00\x00\x81",
            b"\x89\x53\x9a\x05\x4d\x50\x43\x33\x32\x30\x20\x00\x2c\x00\x02\x01\x39\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00",
        ]

        # Act
        idn = self._instr.get_idn()

        # Assert
        self.assertEqual(idn.vendor, expected_idn[0])
        self.assertEqual(idn.model, expected_idn[1])
        self.assertEqual(idn.serial, expected_idn[2])
        self.assertEqual(idn.version, expected_idn[3])

        self._transport_mock.write.assert_called_once_with(
            bytearray(b"\x05\x00\x00\x00P\x01")
        )
        self._transport_mock.read.assert_has_calls(
            [
                unittest.mock.call(nbytes=6, timeout=1.0),
                unittest.mock.call(nbytes=84, timeout=1.0),
            ]
        )


if __name__ == "__main__":
    unittest.main()
