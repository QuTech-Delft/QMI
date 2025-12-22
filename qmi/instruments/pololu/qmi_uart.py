import time

import busio  # mypy: ignore

from qmi.core.exceptions import QMI_InvalidOperationException


class QMI_Uart(busio.UART):
    """Extension of the class to make compatible with QMI_Transport calls.

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
        """The instrument is opened already at the __init__."""
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

        An exception is raised if the transport is closed from the remote
        side before all bytes could be written.

        Subclasses must override this method, if applicable.
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
        If there are no more bytes to read, QMI_EndOfInputException is raised.

        Subclasses must override this method, if applicable.

        Parameters:
            nbytes:  Maximum number of bytes to read.
            timeout: Maximum time to wait (in seconds).

        Returns:
            Received bytes.

        Raises:
            ~qmi.core.exceptions.QMI_EndOfInputException: If the transport has been closed on
                the remote side and there are no more bytes to read.
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
            if bytes_read == nbytes:
                break

            # Check on remaining buffer and adjust read batch size if necessary.
            if bytes_read + batch > nbytes:
                buffer = self.readinto(buffer, nbytes=nbytes - bytes_read)
                break

            if time.time() - start_time > timeout:
                break

        return buffer

    def discard_read(self) -> None:
        """Discard all bytes that are immediately available for reading."""
        self.readline()  # Warning! This might block if there is nothing to read.
