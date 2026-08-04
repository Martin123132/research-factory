"""Provider-neutral front door for the Research Factory control plane.

This package adds discovery, diagnostics and portable construction evidence.
It delegates governed state transitions to :mod:`control_plane`; it is not a
second scientific state machine.
"""

ENGINE_VERSION = "0.1.0"

__all__ = ["ENGINE_VERSION"]
