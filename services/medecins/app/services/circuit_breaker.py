import time
from enum import Enum
from typing import Optional

from services.logger_service import logger_service


class CircuitState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"  # Circuit is open, requests are blocked
    HALF_OPEN = "half-open"  # Testing if service is back to normal


class CircuitBreaker:
    """
    Implementation of the Circuit Breaker pattern.

    Tracks failures in external service calls and prevents further calls
    when the service appears to be malfunctioning.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        half_open_max_calls: int = 1,
    ):
        """
        Initialize the circuit breaker.

        Args:
            name: Name of the circuit (used for logging)
            failure_threshold: Number of consecutive failures before opening the circuit
            recovery_timeout: Seconds to wait before attempting recovery
            half_open_max_calls: Maximum number of test calls in half-open state
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time: Optional[float] = None
        self.half_open_calls = 0

        logger_service.info(
            f"Circuit breaker '{name}' initialized with failure threshold: {failure_threshold}, "
            f"recovery timeout: {recovery_timeout}s"
        )

    def is_closed(self) -> bool:
        """
        Check if the circuit is closed (requests can pass through).

        Returns:
            True if the circuit is closed, False if open
        """
        # If in open state, check if recovery timeout has elapsed
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                # Transition to half-open state
                self._transition_to_half_open()

        # If in half-open state, allow limited requests
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls < self.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False

        # Allow requests in closed state, block in open state
        return self.state == CircuitState.CLOSED

    def record_success(self) -> None:
        """Record a successful operation, potentially closing the circuit."""
        if self.state == CircuitState.HALF_OPEN:
            # Successful call in half-open state, reset the circuit
            self._close()

        # In closed state, just reset the failure count
        self.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed operation, potentially opening the circuit."""
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # Failed test call, reopen the circuit
            self._open()
            return

        # Increment failure counter
        self.failure_count += 1

        # Check if threshold is exceeded
        if (
            self.failure_count >= self.failure_threshold
            and self.state == CircuitState.CLOSED
        ):
            self._open()

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        self._close()

    def _open(self) -> None:
        """Open the circuit."""
        if self.state != CircuitState.OPEN:
            logger_service.warning(
                f"Circuit breaker '{self.name}' opened after {self.failure_count} failures"
            )
            self.state = CircuitState.OPEN
            self.failure_count = (
                self.failure_threshold
            )  # Set to threshold to prevent reset

    def _close(self) -> None:
        """Close the circuit."""
        prev_state = self.state
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.half_open_calls = 0

        if prev_state != CircuitState.CLOSED:
            logger_service.info(
                f"Circuit breaker '{self.name}' closed - service recovered"
            )

    def _transition_to_half_open(self) -> None:
        """Transition from open to half-open state."""
        self.state = CircuitState.HALF_OPEN
        self.half_open_calls = 0
        logger_service.info(
            f"Circuit breaker '{self.name}' half-open - testing if service recovered"
        )
