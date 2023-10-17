VI_ERROR_TMO = int(0xBFFF0015 - 0x100000000)

# correct
vendorid_1 = 0x0699
productid_1 = 0x3000
serialnr_1 = "XYZ"
# incorrect
vendorid_2 = "x0699"
productid_2 = "x3000"
serialnr_2 = "IJK"
# correct
vendorid_3 = 0xbebe
productid_3 = 0xcafe
serialnr_3 = "ABC"
# VISA-style resource strings
visa_str_1 = f"USB1::0x{vendorid_1:04x}::0x{productid_1:04x}::{serialnr_1}::INSTR"
visa_str_2 = f"USB2::{vendorid_2}::{productid_2}::{serialnr_2}::INSTR"
visa_str_3 = f"USBTMC::0x{vendorid_3:04x}::0x{productid_3:04x}::{serialnr_3}::INSTR"


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
    RESOURCES = [visa_str_1, visa_str_2, visa_str_3]

    def open_resource(self, visa_resource):
        return visa_resource

    def list_resources(self):
        return self.RESOURCES


class errors:
    VisaIOError = VisaIOError
    VI_ERROR_TMO = VI_ERROR_TMO
