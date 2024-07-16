#! /usr/bin/env python3
import logging
import time
import unittest

import qmi
from qmi.core.config_defs import CfgQmi, CfgContext
from qmi.core.context import QMI_Context, QMI_Instrument
from qmi.core.exceptions import QMI_RuntimeException, QMI_Exception, QMI_TaskRunException, QMI_UsageException, \
    QMI_InvalidOperationException, QMI_ConfigurationException, QMI_UnknownNameException
from qmi.core.rpc import rpc_method
from qmi.core.task import QMI_Task
from qmi.core.pubsub import QMI_Signal, QMI_SignalReceiver


SPEED_OF_LIGHT = 2998792458


class MyContextTestClass(QMI_Instrument):

    def __init__(self, context: QMI_Context, name: str) -> None:
        super().__init__(context, name)
        self.frequency = 2.0

    @rpc_method
    def get_wavelength(self) -> float:
        """This is some get_method."""
        return SPEED_OF_LIGHT / self.frequency

    @rpc_method
    def set_frequency(self, f: float) -> None:
        """This is some set_method."""
        if f <= 0.0:
            raise ValueError("Value must be positive!")

        self.frequency = f


class TestMultipleContextsSimple(unittest.TestCase):

    def test_multiple_contexts(self):
        """ Test that multiple contexts can be started simultaneously."""
        c1 = QMI_Context("c1", config=None)
        c2 = QMI_Context("c2", config=None)
        c3 = QMI_Context("c3", config=None)

        c1.start()
        c2.start()
        c3.start()

        time.sleep(1.0)
        # Get info from the contexts and see that the name is correct and that they are all active
        contexts = [c1, c2, c3]
        for e, context in enumerate(contexts):
            name = context.info().split("\'")[1]
            self.assertEqual(name, "c{}".format(e + 1))
            self.assertTrue(context._active)

        for con in c1.get_rpc_object_descriptors():
            self.assertEqual(con.address.context_id, "c1")
            self.assertEqual(con.category, "context")

        # Stop the contexts and see that they all stop
        c1.stop()
        c2.stop()
        c3.stop()
        for context in contexts:
            self.assertFalse(context._active)

    def test_invalid_context_names(self):
        """Test that invalid object names raise exceptions."""
        too_long = ""
        for _ in range(64):
            too_long += "a"

        with self.assertRaises(QMI_UsageException):
            QMI_Context("#@%^", config=None)

        with self.assertRaises(QMI_UsageException):
            QMI_Context(too_long, config=None)


class TestMultipleContextsSpecial(unittest.TestCase):

    def setUp(self):
        config = CfgQmi(
            contexts={
                "c1": CfgContext(host="localhost", tcp_server_port=12345),
                "c2": CfgContext(host="localhost", tcp_server_port=12346),
                "c3": CfgContext(tcp_server_port=0)
            }
        )
        self.c1 = QMI_Context("c1", config=config)
        self.c2 = QMI_Context("c2", config=config)
        self.c3 = QMI_Context("c3", config=None)

    def tearDown(self) -> None:
        # Stop the contexts
        if self.c1._active:
            self.c1.stop()

        if self.c2._active:
            self.c2.stop()

        if self.c3._active:
            self.c3.stop()

    def test_multiple_context_configs(self):
        """Try to connect to this peer without giving a peer address. The config has host and port so it should work.
        Then try to connect to this peer without giving a peer address. The config is None, so exception should be
        raised."""
        self.c1.start()
        self.c2.start()
        self.c3.start()

        self.c1.connect_to_peer("c2")  # This should work fine as config has host name and port.
        with self.assertRaises(QMI_UnknownNameException):
            self.c3.connect_to_peer("c2")  # This should fail as for c3 config is None.

    def test_get_tcp_server_port(self):
        """See that we can get the correct port number form active context and 0 from non-active."""
        self.c1.start()
        port1 = self.c1.get_tcp_server_port()
        self.assertEqual(port1, 12345)

        port2 = self.c2.get_tcp_server_port()
        self.assertEqual(port2, 0)


class TestMultipleContextsPeers(unittest.TestCase):

    def test_connect_to_peers(self):
        """Try to connect to multiple peers with the `start()` command."""
        config = {
            "c1": {"host": "localhost", "tcp_server_port": 12345},
            "c2": {"host": "localhost", "tcp_server_port": 12346},
            "c3": {"tcp_server_port": 0, "connect_to_peers": ["c1", "c2"]}
        }

        c1 = QMI_Context("c1", config=CfgQmi(contexts={"c1": CfgContext(host="localhost", tcp_server_port=12345)}))
        c2 = QMI_Context("c2", config=CfgQmi(contexts={"c2": CfgContext(host="localhost", tcp_server_port=12346)}))
        c1.start()
        c2.start()

        qmi.start("c3", context_cfg=config)
        contexts = qmi.get_configured_contexts()
        expect_contexts = {
            "c1": CfgContext(host="localhost", tcp_server_port=12345),
            "c2": CfgContext(host="localhost", tcp_server_port=12346),
            "c3": CfgContext(tcp_server_port=0, connect_to_peers=["c1", "c2"])
        }
        qmi.stop()
        c1.stop()
        c2.stop()

        self.assertEqual(contexts, expect_contexts)


class TestQMIContextClass(unittest.TestCase):

    def setUp(self):
        # Start two contexts.
        config = CfgQmi(
            contexts={
                "c1": CfgContext(tcp_server_port=0),
                "c2": CfgContext(tcp_server_port=0)
            }
        )

        c1 = QMI_Context("c1", config)
        c1.start()
        c1_port = c1.get_tcp_server_port()

        c2 = QMI_Context("c2", config)
        c2.start()
        c2_port = c2.get_tcp_server_port()

        # Note: Connecting to "localhost" on Windows can give 1 second delay
        # because IPv6 is attempted before IPv4.
        # This problem does not occur when connecting to "127.0.0.1".

        # Connect c1 to c2.
        c1.connect_to_peer("c2", "localhost:{}".format(c2_port))

        # Connect c2 to c1.
        c2.connect_to_peer("c1", "127.0.0.1:{}".format(c1_port))

        self.c1 = c1
        self.c2 = c2

    def tearDown(self):

        if self.c1._active:
            self.c1.stop()

        self.c2.stop()

        self.c1 = None
        self.c2 = None

    def test_has_peer_context(self):
        """See that a context with specific name is connected as a peer."""
        has_it = self.c1.has_peer_context("c2")
        self.assertTrue(has_it)

    def test_connect_context_name_mismatch(self):
        """See that an exception is raised if the context names do not exist or do not match"""
        c2_port = self.c2.get_tcp_server_port()
        with self.assertRaises(QMI_RuntimeException):
            self.c1.connect_to_peer("aap", "127.0.0.1:{}".format(c2_port))

    def test_connect_to_peer_without_address_and_no_config(self):
        """Try to connect to this peer without giving a peer address and no host. See that exception is raised."""
        with self.assertRaises(QMI_ConfigurationException):
            self.c1.connect_to_peer("c2")

    def test_connect_duplicate_peer_ignore(self):
        """Do nothing as we are already connected to this peer and we choose to ignore it."""
        c2_port = self.c2.get_tcp_server_port()
        self.c1.connect_to_peer("c2", "localhost:{}".format(c2_port), ignore_duplicate=True)

    def test_connect_inactive_context_cannot_connect_to_peer(self):
        """Raise an exception as we are trying to connect an inactive context"""
        self.c1.stop()
        c2_port = self.c2.get_tcp_server_port()
        with self.assertRaises(QMI_InvalidOperationException):
            self.c1.connect_to_peer("c2", "localhost:{}".format(c2_port))

    def test_disconnect_inactive_context_raises_exception(self):
        """Raise an exception as we are trying to disconnect an inactive context"""
        self.c1.stop()
        with self.assertRaises(QMI_InvalidOperationException):
            self.c1.disconnect_from_peer("c2")

    def test_connect_duplicate_peer_raises_exception(self):
        """Raise an exception as we are already connected to this peer"""
        c2_port = self.c2.get_tcp_server_port()
        with self.assertRaises(QMI_UsageException):
            self.c1.connect_to_peer("c2", "localhost:{}".format(c2_port))


class TestMultipleUsersToInstrument(unittest.TestCase):

    def setUp(self):
        # Suppress logging.
        logging.getLogger("qmi.core.rpc").setLevel(logging.CRITICAL)

        # Start two contexts with the first one creating the "instrument".
        config = CfgQmi(
            contexts={
                "c1": CfgContext(tcp_server_port=0),
                "c2": CfgContext(tcp_server_port=0)
            }
        )
        self.c1 = QMI_Context("c1", config=config)
        self.c1.start()
        self.c2 = QMI_Context("c2", config=config)
        self.c2.start()

        self.instr_proxy_server = self.c1.make_instrument("instr", MyContextTestClass)

        # Connect second context to first.
        c1_port = self.c1.get_tcp_server_port()
        self.c2.connect_to_peer("c1", f"localhost:{c1_port}")
        self.instr_proxy_client = self.c2.get_instrument("c1.instr")

    def tearDown(self):
        self.c1.stop()
        self.c2.stop()

        self.c1 = None
        self.c2 = None

        logging.getLogger("qmi.core.rpc").setLevel(logging.NOTSET)

    def test_01_get_instrument(self):
        """Test that second proxy to instrument can send commands without problems."""
        frequency = 2.0
        self.instr_proxy_client.set_frequency(frequency)

        wl = self.instr_proxy_server.get_wavelength()
        self.assertEqual(wl, SPEED_OF_LIGHT / frequency)

    def test_02_check_acquire_and_unlock_object(self):
        """Test that the acquire, is locked enquiry, and release work."""
        # Test initial state is False
        ans = self.instr_proxy_client.is_locked()
        self.assertFalse(ans)
        # Test that acquiring lock changes state to True
        success = self.instr_proxy_client.lock()
        self.assertTrue(success)
        ans = self.instr_proxy_client.is_locked()
        self.assertTrue(ans)
        # Test that releasing the lock changes state back to False
        success = self.instr_proxy_client.unlock()
        self.assertTrue(success)
        ans = self.instr_proxy_client.is_locked()
        self.assertFalse(ans)

    def test_03_lock_object_on_first_proxy(self):
        """Test that second proxy to instrument fails to get data after first proxy acquires a lock."""
        # Set lock
        success = self.instr_proxy_client.lock()
        self.assertTrue(success)
        # See that the second proxy fails to command the instrument
        with self.assertRaises(QMI_RuntimeException):
            self.instr_proxy_server.set_frequency(1.0)

    def test_04_acquire_and_unlock_object_on_first_proxy(self):
        """Test that second proxy to instrument can send commands data after first proxy releases the lock."""
        # set lock and check
        self.instr_proxy_client.lock()
        ans = self.instr_proxy_server.is_locked()
        self.assertTrue(ans)
        # release the lock and check
        self.instr_proxy_client.unlock()
        ans = self.instr_proxy_server.is_locked()
        self.assertFalse(ans)
        # See that it works again
        frequency = 4.0
        self.instr_proxy_server.set_frequency(frequency)
        wl = self.instr_proxy_client.get_wavelength()
        self.assertEqual(wl, SPEED_OF_LIGHT / frequency)


class TestMultipleUsersToInstrumentWithLock(unittest.TestCase):

    def setUp(self):
        # Suppress logging.
        logging.getLogger("qmi.core.rpc").setLevel(logging.CRITICAL)

        # Start two contexts with the first one creating the "instrument".
        config = CfgQmi(
            contexts={
                "c1": CfgContext(tcp_server_port=0),
                "c2": CfgContext(tcp_server_port=0)
            }
        )
        self.c1 = QMI_Context("c1", config=config)
        self.c1.start()
        self.c2 = QMI_Context("c2", config=config)
        self.c2.start()

        self.instr_proxy_server = self.c1.make_rpc_object("instr", MyContextTestClass)

        # Connect second context to first.
        c1_port = self.c1.get_tcp_server_port()
        self.c2.connect_to_peer("c1", f"localhost:{c1_port}")
        self.instr_proxy_client = self.c2.get_rpc_object_by_name("c1.instr")

    def tearDown(self):
        self.c1.stop()
        self.c2.stop()

        self.c1 = None
        self.c2 = None

        logging.getLogger("qmi.core.rpc").setLevel(logging.NOTSET)

    def test_01_check_command_before_lock_works(self):
        """Test that first proxy to instrument can send commands without problems."""
        frequency = 2.0
        self.instr_proxy_client.set_frequency(frequency)
        wl = self.instr_proxy_client.get_wavelength()
        self.assertEqual(wl, SPEED_OF_LIGHT / frequency)

    def test_02_cannot_lock_object_for_already_locked_instrument(self):
        """Test that first proxy to instrument fails to acquire lock after second proxy acquires a lock."""
        self.instr_proxy_server.lock()
        success = self.instr_proxy_client.lock()
        self.assertFalse(success)

    def test_03_cannot_unlock_object_for_already_locked_instrument(self):
        """Test that first proxy to instrument fails to release lock after second proxy acquires a lock."""
        self.instr_proxy_server.lock()
        success = self.instr_proxy_client.unlock()
        self.assertFalse(success)

    def test_04_command_after_second_proxy_lock_raises_exception(self):
        """Test that first proxy to instrument fails to set/get data after second proxy acquires a lock."""
        self.instr_proxy_server.lock()

        with self.assertRaises(QMI_RuntimeException):
            self.instr_proxy_client.set_frequency(1.0)

        with self.assertRaises(QMI_RuntimeException):
            self.instr_proxy_client.get_wavelength()

    def test_05_force_release_locked_instrument(self):
        """Test that first proxy's lock can be released forcefully and is available for the second afterwards."""
        success = self.instr_proxy_client.lock()
        self.assertTrue(success)
        self.assertTrue(self.instr_proxy_server.is_locked())

        # Force unlock.
        self.instr_proxy_server.force_unlock()
        self.assertFalse(self.instr_proxy_server.is_locked())

        # And check that trying to lock it no longer fails.
        success = self.instr_proxy_server.lock()
        self.assertTrue(success)
        self.assertTrue(self.instr_proxy_server.is_locked())


class MyContextTaskController(QMI_Task):
    sig_sample = QMI_Signal([float])
    lock = False

    def __init__(self, task_runner, name, instrument, sample_time):
        super().__init__(task_runner, name)

        self._instr = instrument
        self._sample_time = sample_time

    def run(self):
        """Main loop."""
        try:
            self._instr.lock()

            # Sweep through optical range of wavelengths (350-700nm)
            blue_frequency = SPEED_OF_LIGHT / 350e-9
            red_frequency = SPEED_OF_LIGHT / 700e-9
            sweep_steps = 8
            step_size = (red_frequency - blue_frequency) / (sweep_steps - 1)
            for step in range(sweep_steps):
                frequency = blue_frequency + step * step_size
                self._instr.set_frequency(frequency)
                wl = self._instr.get_wavelength()
                self.sig_sample.publish(wl)
                time.sleep(self._sample_time)

        except QMI_Exception as exc:
            raise QMI_Exception from exc

        finally:
            if self._instr.is_locked():
                self._instr.unlock()


class TestTasksAndUserToInstrumentWithLock(unittest.TestCase):

    def setUp(self):
        # Suppress logging.
        logging.getLogger("qmi.core.rpc").setLevel(logging.CRITICAL)
        logging.getLogger("qmi.core.task").setLevel(logging.ERROR)

        # Start a context with creating an "instrument".
        self.c1 = QMI_Context("instr_server", config=None)
        self.c1.start()
        self.instr = self.c1.make_instrument("instr", MyContextTestClass)

        # We need a client to talk to the created instrument (using self.instr directly does not work)
        client = self.c1.get_instrument("instr_server.instr")

        # Then prepare a task within that context.
        self.controller = self.c1.make_task("controller", MyContextTaskController, client, 0.1)

        # Create a signal subscriber
        self.receiver = QMI_SignalReceiver()
        self.publisher_proxy = self.c1.get_task("instr_server.controller")
        self.publisher_proxy.sig_sample.subscribe(self.receiver)
        self.wait_timeout = 0.1

    def tearDown(self) -> None:
        # Close task and QMI
        try:
            if self.controller.is_running():
                self.controller.stop()
                self.controller.join()

        except QMI_TaskRunException:
            pass

        finally:
            self.c1.stop()
            logging.getLogger("qmi.core.rpc").setLevel(logging.NOTSET)
            logging.getLogger("qmi.core.task").setLevel(logging.NOTSET)

    def test_01_task_runs_normally(self):
        """Test that the task runs as expected."""
        expected = [3.5e-07, 3.77e-07, 4.08e-07, 4.45e-07, 4.9e-07, 5.44e-07, 6.13e-07, 7e-07]
        self.controller.start()
        for s in range(len(expected)):
            # Wait that data is produced and check that we are still running.
            while not self.receiver.has_signal_ready() and self.controller.is_running():
                time.sleep(self.wait_timeout)

            signal = self.receiver.get_next_signal(timeout=self.wait_timeout)
            self.assertEqual(expected[s], round(signal.args[0], 9))

    def test_02_task_cannot_run_due_to_instrument_locked(self):
        """The instrument is locked before running the task, forcing the task to except."""
        self.instr.lock()

        with self.assertRaises(QMI_TaskRunException):
            self.controller.start()
            time.sleep(self.wait_timeout)
            self.controller.stop()
            self.controller.join()

        # See that controller did not do anything to set frequencies
        wl = self.instr.get_wavelength()
        self.assertEqual(SPEED_OF_LIGHT / 2.0, wl)

    def test_03_task_runs_with_locking_the_instrument(self):
        """The task locks the instrument and runs normally. The instrument cannot be communicated
        from the regular context."""
        self.controller.start()
        time.sleep(self.wait_timeout)
        with self.assertRaises(QMI_RuntimeException):
            self.instr.set_frequency(2.0)


if __name__ == "__main__":
    unittest.main()
