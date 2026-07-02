"""Reconnect supervision for foreground Joy-Con sessions."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import time

from joyio.config.models import ReconnectConfig
from joyio.devices import JoyConInput


AcquireInputs = Callable[[], Sequence[JoyConInput]]
RunSession = Callable[[Sequence[JoyConInput]], None]
RetryCallback = Callable[[int, float, Exception], None]


def _retry_delay(policy: ReconnectConfig, attempts: int) -> float:
    delay = policy.initial_delay
    for _ in range(attempts - 1):
        delay = min(policy.max_delay, delay * policy.multiplier)
        if delay >= policy.max_delay:
            break
    return delay


def run_with_reconnect(
    acquire_inputs: AcquireInputs,
    run_session: RunSession,
    policy: ReconnectConfig,
    *,
    recoverable_errors: tuple[type[Exception], ...],
    on_retry: RetryCallback | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Run sessions until completion, retrying recoverable failures with backoff."""

    attempts = 0
    while True:
        try:
            inputs = acquire_inputs()
            # A complete acquisition breaks a chain of connection failures. A later
            # evdev disconnect starts a new retry sequence from the initial delay.
            attempts = 0
            run_session(inputs)
            return
        except recoverable_errors as error:
            if not policy.enabled:
                raise
            attempts += 1
            if policy.max_attempts is not None and attempts > policy.max_attempts:
                raise
            delay = _retry_delay(policy, attempts)
            if on_retry is not None:
                on_retry(attempts, delay, error)
            sleep(delay)
