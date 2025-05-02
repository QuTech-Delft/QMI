"""Mock module to import _posixsubprocess in Windows env."""

def fork_exec(*args, **kwargs):
    return 123  # PID number
