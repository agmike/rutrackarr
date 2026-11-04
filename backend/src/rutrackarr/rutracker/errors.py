class RuTrackerError(Exception):
    """A RuTracker interaction failed; the message is shown to the user."""


class NotConfiguredError(RuTrackerError):
    pass


class CloudflareError(RuTrackerError):
    pass


class LoginFailedError(RuTrackerError):
    pass


class MaintenanceError(RuTrackerError):
    """The site shows its maintenance page; nothing to do but wait (no re-login)."""
