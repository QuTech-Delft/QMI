import unittest
from unittest.mock import MagicMock, Mock, call, patch
import logging

import qmi.core.exceptions

import qmi.instruments
from tests.patcher import PatcherQmiContext as QMI_Context


# Mock import "mcculw"
class mcculw:
    ul = None
    enums = None
    structs = None


class TestFosUnix(unittest.TestCase):
    """ Unit tests for Bristol FOS. """

    UNIQUE_ID = 'DEADBEAF'

    @patch("sys.platform", "linux")
    def setUp(self):
        logging.getLogger("qmi.instruments.bristol.fos").setLevel(logging.CRITICAL)
        import qmi.instruments.bristol.fos

        # Substitute a mock object in place of the "uldaq" module.
        # This must be done BEFORE the FOS driver runs "import uldaq".
        with patch.dict("sys.modules", {"uldaq": Mock()}):
            # Trigger lazy import of the uldaq module.
            qmi.instruments.bristol.fos._import_modules()

        # Patch device descriptor
        self.wrong_dev_desc = Mock()
        self.wrong_dev_desc.unique_id = self.UNIQUE_ID[::-1]
        self.dev_desc = Mock()
        self.dev_desc.unique_id = self.UNIQUE_ID
        patcher = patch('qmi.instruments.bristol.fos.uldaq.get_daq_device_inventory',
                        side_effect=[[self.wrong_dev_desc, self.dev_desc]])
        _ = patcher.start()
        self.addCleanup(patcher.stop)

        # Patch device
        self.device_mock = Mock()
        patcher = patch('qmi.instruments.bristol.fos.uldaq.DaqDevice',
                        return_value=self.device_mock)
        self.device_init = patcher.start()
        self.addCleanup(patcher.stop)

        # Start QMI patcher
        self.qmi_ctx = QMI_Context("test_fos")
        self.qmi_ctx.start("test_fos")

    def tearDown(self):
        # Stop QMI
        self.qmi_ctx.stop()
        logging.getLogger("qmi.instruments.bristol.fos").setLevel(logging.NOTSET)

    def test_open_close(self):
        """Test open & close of the FOS."""
        from qmi.instruments.bristol import Bristol_Fos

        # Pull data types from the mocked uldaq module.
        DigitalPortType = qmi.instruments.bristol.fos.uldaq.DigitalPortType
        DigitalDirection = qmi.instruments.bristol.fos.uldaq.DigitalDirection

        # Arrange
        expected_calls = [
            call.connect(),
            call.get_dio_device(),
            call.disconnect(),
            call.release()
        ]

        expected_port_config = (
            DigitalPortType.FIRSTPORTA, DigitalDirection.OUTPUT
        )

        # Act
        with patch("qmi.instruments.bristol.fos.sys.platform", "linux"):
            fos: Bristol_Fos = Bristol_Fos(self.qmi_ctx, "fosser", self.UNIQUE_ID)
            fos.open()
            fos.close()

        # Assert
        self.assertEqual((self.dev_desc,), self.device_init.call_args[0])
        self.assertEqual(expected_calls, self.device_mock.method_calls)
        self.assertTupleEqual(expected_port_config,
                              self.device_mock.get_dio_device.return_value.d_config_port.call_args[0])

    def test_device_not_found(self):
        """Test exception if device not found."""
        from qmi.instruments.bristol import Bristol_Fos
        # Act
        with patch("qmi.instruments.bristol.fos.sys.platform", "linux"):
            fos: Bristol_Fos = Bristol_Fos(self.qmi_ctx, "fosser", "wrong")

        # Assert
        with self.assertRaises(ValueError):
            fos.open()

    def test_device_connection_errors(self):
        """Test exception if device has connection issues."""
        from qmi.instruments.bristol import Bristol_Fos
        # Arrange
        expected_calls = [
            call.connect(),
            call.get_dio_device(),
            call.disconnect(),
            call.release()
        ]
        self.device_mock.get_dio_device = Mock(return_value=BaseException)
        # Act
        with patch("qmi.instruments.bristol.fos.sys.platform", "linux"):
            fos: Bristol_Fos = Bristol_Fos(self.qmi_ctx, "fosser", self.UNIQUE_ID)
        # Assert
        with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
            fos.open()

        self.assertEqual(expected_calls, self.device_mock.method_calls)

    def test_select_channel(self):
        """Test selecting channel"""
        from qmi.instruments.bristol import Bristol_Fos

        # Pull data types from the mocked uldaq module.
        DigitalPortType = qmi.instruments.bristol.fos.uldaq.DigitalPortType

        # Arrange
        test_channel = 1
        expected_d_out = (
            DigitalPortType.FIRSTPORTA, test_channel - 1
        )

        # Act
        with patch("qmi.instruments.bristol.fos.sys.platform", "linux"):
            with qmi.make_instrument("fosser", Bristol_Fos, self.UNIQUE_ID) as fos:
                fos.select_channel(test_channel)

        # Assert
        self.assertTupleEqual(expected_d_out, self.device_mock.get_dio_device.return_value.d_out.call_args[0])

    def test_bad_channel(self):
        """Test bad channel"""
        from qmi.instruments.bristol import Bristol_Fos
        # Act & assert
        with self.assertRaises(ValueError):
            with patch("qmi.instruments.bristol.fos.sys.platform", "linux"):
                with qmi.make_instrument("fosser", Bristol_Fos, self.UNIQUE_ID) as fos:
                    fos.select_channel(0)


@patch("qmi.instruments.bristol.fos.sys.platform", "win32")
class TestFosWindows(unittest.TestCase):
    """ Unit tests for Bristol FOS. """

    UNIQUE_ID = 'DEADBEAF'

    @patch("qmi.instruments.bristol.fos.sys.platform", "win32")
    def setUp(self):
        logging.getLogger("qmi.instruments.bristol.fos").setLevel(logging.CRITICAL)
        # Patch device descriptor
        self.dev_desc = Mock()
        self.dev_desc.unique_id = self.UNIQUE_ID
        self.wrong_dev_desc = Mock()
        self.wrong_dev_desc.unique_id = self.UNIQUE_ID[::-1]
        # Substitute a mock object in place of the "mcculw" module.
        # This must be done BEFORE the FOS driver runs "import mcculw".
        self.mcculw_mock = MagicMock(autospec=mcculw)
        with patch.dict("sys.modules", {
            "mcculw": self.mcculw_mock,
        }):
            # Trigger lazy import of the mcculw module.
            qmi.instruments.bristol.fos._import_modules()

            self.ulpatcher = patch(
                "qmi.instruments.bristol.fos.ul.get_daq_device_inventory",
            )
            self.ulpatcher.start()

        self.addCleanup(self.ulpatcher.stop)

        # Start QMI patcher
        self.qmi_ctx = QMI_Context("test_fos")
        self.qmi_ctx.start("test_fos")

    def tearDown(self):
        # Stop QMI
        self.qmi_ctx.stop()
        logging.getLogger("qmi.instruments.bristol.fos").setLevel(logging.NOTSET)

    def test_open_close(self):
        """Test open & close of the FOS."""
        # Arrange
        from qmi.instruments.bristol import Bristol_Fos
        board_id = 0

        fos: Bristol_Fos = Bristol_Fos(self.qmi_ctx, "fosser", self.UNIQUE_ID)

        self.ulpatcher.target.get_daq_device_inventory.return_value = [self.wrong_dev_desc, self.dev_desc]
        self.ulpatcher.target.d_config_port.side_effect = [None]

        # Act
        with patch("qmi.instruments.bristol.fos.ul.get_board_number", return_value=board_id) as bid_patch:
            fos.open()

        fos.close()

        # Assert
        self.ulpatcher.target.get_daq_device_inventory.assert_called()
        self.ulpatcher.target.create_daq_device.assert_called()
        self.assertEqual(1, bid_patch.call_count)
        self.ulpatcher.target.d_config_port.assert_called()
        self.ulpatcher.target.release_daq_device.assert_called()

    def test_device_not_found(self):
        """Test exception if device not found."""
        # Arrange
        from qmi.instruments.bristol import Bristol_Fos
        # Act
        fos: Bristol_Fos = Bristol_Fos(self.qmi_ctx, "fosser", "wrong")

        # Assert
        with self.assertRaises(ValueError):
            fos.open()

    def test_invalid_board_number(self):
        """Test assertion error is raised, if the board number is not valid."""
        # Arrange
        from qmi.instruments.bristol import Bristol_Fos
        invalid_bids = [-1, 100]
        # Act
        for bid in invalid_bids:
            # Assert
            with self.assertRaises(AssertionError):
                fos = Bristol_Fos(self.qmi_ctx, "fosser", self.UNIQUE_ID, board_id=bid)
                fos._is_open = True
                fos.close()

            fos: Bristol_Fos = Bristol_Fos(self.qmi_ctx, "fosser", self.UNIQUE_ID)
            with self.assertRaises(AssertionError):
                fos.fos.board_id = bid

    def test_device_connection_errors(self):
        """Test exception if device has connection issues."""
        from qmi.instruments.bristol import Bristol_Fos
        # Arrange
        self.ulpatcher.target.get_daq_device_inventory.return_value = [self.dev_desc]
        board_id = 2
        # Act
        fos: Bristol_Fos = Bristol_Fos(self.qmi_ctx, "fosser", self.UNIQUE_ID)
        fos.fos.board_id = board_id

        with patch("qmi.instruments.bristol.fos.ul.get_board_number", return_value=board_id) as bid_patch:
            # Assert
            self.ulpatcher.target.d_config_port.side_effect = [Exception("Fail")]
            with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
                fos.open()

        self.ulpatcher.target.create_daq_device.assert_called()
        self.assertEqual(1, bid_patch.call_count)
        self.ulpatcher.target.d_config_port.assert_called()
        self.ulpatcher.target.release_daq_device.assert_called()

    def test_select_channel(self):
        """Test selecting channel."""
        from qmi.instruments.bristol import Bristol_Fos

        # Pull data types from the mocked uldaq module.
        DigitalPortType = qmi.instruments.bristol.fos.enums.DigitalPortType
        # Arrange
        test_channel = 1
        board_id = 0
        self.ulpatcher.target.d_config_port.side_effect = [None]
        self.ulpatcher.target.get_daq_device_inventory.return_value = [self.dev_desc]
        # Act
        with patch("qmi.instruments.bristol.fos.ul.get_board_number", return_value=board_id):
            with qmi.make_instrument("fosser", Bristol_Fos, self.UNIQUE_ID) as fos:
                fos.select_channel(test_channel)

        # Assert
        self.ulpatcher.target.d_out.assert_called_once_with(
            board_id, DigitalPortType.FIRSTPORTA, test_channel - 1
        )

    def test_bad_channel(self):
        """Test bad channel."""
        from qmi.instruments.bristol import Bristol_Fos
        # Act & assert
        board_id = 0
        self.ulpatcher.target.get_daq_device_inventory.return_value = [self.dev_desc]
        with self.assertRaises(ValueError):
            with patch("qmi.instruments.bristol.fos.ul.get_board_number", return_value=board_id):
                with qmi.make_instrument("fosser", Bristol_Fos, self.UNIQUE_ID) as fos:
                    fos.select_channel(0)
