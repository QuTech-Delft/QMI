"""Implementation of class KeyboardReader.

The KeyboardReader provides a way to read lines from the keyboard without blocking
in a platform-independent way.
"""

import sys

# We implement a platform-specific _PollKeyboard class that provides a 'poll_line' method to
# fetch a single line of input in a non-blocking way.
#
# The reason that we implement this as a class is that in Windows, the 'msvcrt' API doesn't
# do buffering for us, so we have to buffer the characters ourselves.
#
# To allow identical interfaces between Windows and Unix platforms, we begrudgingly implement the same
# class-based interface in Unix, even though in Unix, buffering is handled by the OS.

if sys.platform.startswith("win"):

    # _PollKeyboard class for the Windows platform.

    import msvcrt  # Only exists in Windows.

    class _PollKeyboard:
        """Internal helper class to read from the keyboard on Windows platforms."""

        def __init__(self) -> None:
            self._buffer = ""

        def poll_line(self) -> str:
            """Poll for a single line of input on the Windows platform.

            Returns:
                An empty string if no Enter-terminated line is available;
                a non-empty string containing a line and ending in '\n' if an Enter-terminated string is available.
            """

            # We read up to 256 characters using msvcrt's getwch() method, as long as input is available.
            #
            # In Windows, the Enter key produces an end-of-line character ('\r').
            # If this character is detected, we the buffer followed by a newline character ('\n') instead.

            i = 0
            while (i < 256) and msvcrt.kbhit():
                i += 1
                c = msvcrt.getwch()
                if c == '\r':
                    # We replace the carriage return character ('\r') by a linefeed character ('\n').
                    ret = self._buffer + '\n'
                    self._buffer = ""  # Clear the buffer
                    return ret
                else:
                    self._buffer += c
            return ""

else:
    # _PollKeyboard class for Unix platforms (including macOS which is a BSD derivative).

    import select

    class _PollKeyboard:
        """Internal helper class to read from the keyboard on Unix platforms."""

        def poll_line(self) -> str:
            """Poll for a single line of input on a Unix platform.

            Returns:
                An empty string if no Enter-terminated line is available;
                a non-empty string containing a line and ending in '\n' if an Enter-terminated string is available.
            """

            # Use select() to determine if a line of input is available.
            #
            # The OS does the line buffering for us. Hitting 'Enter' on the keyboard will insert a
            # newline character ('\n') into the buffer, and will make the selector generate an event.
            #
            # We use the "select" module instead of the "selectors" module
            # because the "selectors" module raises a PermissionError
            # when stdin has been redirected from /dev/null. This happens
            # with server processes when they run in the background.

            (rl, wl, xl) = select.select([sys.stdin], [], [], 0)
            if rl:
                return sys.stdin.readline()
            else:
                return ""


class KeyboardReader:
    """A class that implements non-blocking read of single lines from the keyboard."""

    def __init__(self) -> None:
        self._poll_keyboard = _PollKeyboard()  # Instantiate platform-dependent keyboard line poller.

    def poll_line(self) -> str:
        """Read a line from the keyboard without blocking.

        If keyboard input is waiting, return a string containing one line of input.
        Otherwise, return an empty string.
        """
        return self._poll_keyboard.poll_line()

    def clear_buffer(self) -> None:
        """Remove pending data from the keyboard input buffer."""
        while self.poll_line():
            pass

    def poll_quit(self) -> bool:
        """Check if the user has typed "Q" to stop the measurement.

        Return True if the user has typed "Q", otherwise return False.
        """
        line = self.poll_line()
        if line:
            if line.strip().upper() == "Q":
                return True
            else:
                print("Measurement in progress - type 'Q' followed by Enter to quit.")
        return False
