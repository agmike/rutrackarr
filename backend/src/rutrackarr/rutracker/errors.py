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


class UnreachableError(RuTrackerError):
    """No answer from RuTracker at all (connection refused, timeout, TLS)."""


class UnexpectedPageError(RuTrackerError):
    """A page we don't recognise — reported, never treated as an expired session."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class CaptchaRequiredError(LoginFailedError):
    pass


def unavailable(e: Exception) -> bool:
    """RuTracker itself is down for now (unreachable, maintenance, a 5xx error page) — not a
    problem on our side (login, captcha, FlareSolverr, configuration)."""
    if isinstance(e, (UnreachableError, MaintenanceError)):
        return True
    return isinstance(e, UnexpectedPageError) and (e.status or 0) >= 500
