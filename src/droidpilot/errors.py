"""Error types. Every tool turns these into a one-line result the agent can act on."""

from __future__ import annotations


class DeviceError(RuntimeError):
    """The phone is missing or unauthorised, or a device command failed. Result prefix: ERROR."""


class NeedsHuman(DeviceError):
    """A step only the user can do (PIN, CAPTCHA, OTP). Result prefix: NEEDS_HUMAN."""


class Blocked(DeviceError):
    """The safety guard refused an action. Result prefix: BLOCKED. Retry needs confirm=true."""
