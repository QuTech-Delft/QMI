VI_ERROR_TMO = int(0xBFFF0015 - 0x100000000)


class Error(Exception):
    """Abstract basic exception class for this module."""

    pass


class VisaIOError(Error):
    """Exception class for VISA I/O errors.

    Please note that all values for "error_code" are negative according to the
    specification (VPP-4.3.2, observation 3.3.2) and the NI implementation.

    """

    def __init__(self, error_code: int) -> None:
        abbreviation, description = ("VI_ERROR_TMO", "Timeout expired before operation " "completed.")
        super(VisaIOError, self).__init__(
            "%s (%d): %s" % (abbreviation, error_code, description)
        )
        self.error_code = error_code
        self.abbreviation = abbreviation
        self.description = description

    def __reduce__(self):
        """Store the error code when pickling."""
        return (VisaIOError, (self.error_code,))


class ResourceManager:
    def open_resource(self, visa_resource):
        return visa_resource


class errors:
    VisaIOError = VisaIOError
    VI_ERROR_TMO = VI_ERROR_TMO
