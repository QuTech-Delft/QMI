import time
from queue import Empty

import busio  # type: ignore

from qmi.core.exceptions import QMI_InvalidOperationException


class QMI_Uart(busio.UART):
    """Extension of the class to make compatible with QMI_Transport calls.

    The UART class opens a serial connection behind the scenes, see class binhoHostAdapter in binhoHostAdapter.py.
    The default read and write timeouts are: timeout=0.025, write_timeout=0.05. These are not changeable through the
    API, but would need a workaround through the 'serial' module interface.

    The docstring of busio.readline says a 'line' is read until a _newline_ character, but in `uart.py` we can see that
    ```        while out != "\r":``` is used. Thus, the correct docstring should be that a line is read until a
    _carriage return_ character.

    Attributes:
        READ_BYTE_BATCH_SIZE: The default size of the read buffer, based on <LSB><MSB>.
    """
    READ_BYTE_BATCH_SIZE = 2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._is_open = True

    def _check_is_open(self) -> None:
        """Verify that the transport is open, otherwise raise exception."""
        if not self._is_open:
            raise QMI_InvalidOperationException(
                f"Operation not allowed on closed transport {type(self).__name__}")

    def open(self) -> None:
        """The instrument is opened already at the __init__. Note that if close() -> self.deinit() was called,
        we cannot simply 're-open', but need to make a new instance to open the connection again.
        """
        pass

    def close(self) -> None:
        """Close the transport and de-initialize the device."""
        self._check_is_open()
        self.deinit()
        self._is_open = False

    def write(self, data: bytes) -> None:
        """Write a sequence of bytes to the transport.

        When this method returns, all bytes are written to the transport
        or queued to be written to the transport.

        Parameters:
            data: Bytes to write.
        """
        self._check_is_open()
        super().write(data)

    def read_until_timeout(self, nbytes: int, timeout: float) -> bytes:
        """Read a sequence of bytes from the transport.

        This method blocks until either the specified number of bytes
        are available or the timeout (in seconds) expires, whichever occurs
        sooner.

        If timeout occurs, the partial sequence of available bytes is returned.
        This sequence may be empty if timeout occurs before any byte was available.

        If the transport has been closed on the remote side, any remaining
        input bytes are returned (up to the maximum number of bytes requested).

        Parameters:
            nbytes:  Maximum number of bytes to read.
            timeout: Maximum time to wait (in seconds).

        Returns:
            data: Received bytes.
        """
        self._check_is_open()
        buffer = bytearray()
        batch = self.READ_BYTE_BATCH_SIZE if nbytes > self.READ_BYTE_BATCH_SIZE else nbytes
        bytes_read = 0
        start_time = time.time()
        while bytes_read < nbytes:
            # Extend buffer, for now try in batches (of 1 or more bytes).
            buffer = self.readinto(buffer, nbytes=batch)
            bytes_read += batch
            if time.time() - start_time > timeout:
                break

            if bytes_read == nbytes:
                break

            # Check on remaining buffer and adjust read batch size if necessary.
            if bytes_read + batch > nbytes:
                buffer = self.readinto(buffer, nbytes=nbytes - bytes_read)
                break

        return buffer

    def discard_read(self) -> None:
        """Discard all bytes that are immediately available for reading. As using the read methods from uart.py use
        `Queue.get()`, which means blocking until something is received, we work around this by calling the queue
        without blocking.
        """
        while True:
            try:
                self._uart._nova._rxdQueue.get(block=False)
            except Empty:
                break
