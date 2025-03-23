import functools
import time
import logging
from enum import Enum, auto
from typing import Type, Callable, Any, Optional

from metrics import (
    track_circuit_breaker_state, 
    track_circuit_breaker_failure,
    track_circuit_breaker_success,
    track_circuit_breaker_rejection
)

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = auto()      # Normal operation, requests are allowed
    OPEN = auto()        # Circuit is open, requests will fail fast
    HALF_OPEN = auto()   # Testing if service is healthy again

class CircuitBreaker:
    """Circuit breaker pattern implementation"""
    
    _instances = {}  # Class variable to store instances
    
    def __init__(
        self, 
        name: str = "default",
        failure_threshold: int = 5, 
        recovery_timeout: int = 60,
        expected_exception: Type[Exception] = Exception
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        
        # Store the instance in class variable for tracking
        CircuitBreaker._instances[name] = self
        
        # Initialize metrics for this circuit breaker
        track_circuit_breaker_state(name, "closed")
        
        logger.info(f"Circuit breaker '{name}' initialized (threshold={failure_threshold}, timeout={recovery_timeout}s)")
    
    def __call__(self, func):
        """Decorator implementation"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)
        return wrapper
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute the function with circuit breaker logic"""
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                logger.info(f"Circuit '{self.name}' attempting reset (half-open)")
                self.state = CircuitState.HALF_OPEN
                track_circuit_breaker_state(self.name, "half_open")
            else:
                logger.warning(f"Circuit '{self.name}' is OPEN - failing fast")
                track_circuit_breaker_rejection(self.name)
                raise CircuitBreakerError(
                    f"Circuit '{self.name}' is open"
                )
        
        try:
            result = func(*args, **kwargs)
            
            # On success in half-open state, reset the circuit
            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"Circuit '{self.name}' reset successful - closing circuit")
                self.reset()
            
            # Track success
            track_circuit_breaker_success(self.name)
            return result
            
        except self.expected_exception as e:
            # Record the failure
            self.record_failure()
            raise
            
        except Exception as e:
            # Unexpected exception - don't count towards circuit breaker
            logger.error(f"Unexpected error in circuit '{self.name}': {str(e)}")
            raise
    
    def record_failure(self):
        """Record a failure and check if circuit should open"""
        self.last_failure_time = time.time()
        
        # Track the failure in metrics
        track_circuit_breaker_failure(self.name)
        
        # In half-open state, a single failure opens the circuit again
        if self.state == CircuitState.HALF_OPEN:
            logger.warning(f"Circuit '{self.name}' failed in half-open state - opening circuit")
            self.state = CircuitState.OPEN
            track_circuit_breaker_state(self.name, "open")
            self.failure_count = self.failure_threshold
            return
            
        # In closed state, count failures until threshold
        self.failure_count += 1
        logger.debug(f"Circuit '{self.name}' failure count: {self.failure_count}/{self.failure_threshold}")
        
        if self.failure_count >= self.failure_threshold:
            logger.warning(f"Circuit '{self.name}' exceeded failure threshold - opening circuit")
            self.state = CircuitState.OPEN
            track_circuit_breaker_state(self.name, "open")
    
    def reset(self):
        """Reset the circuit breaker to closed state"""
        logger.info(f"Resetting circuit '{self.name}'")
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        track_circuit_breaker_state(self.name, "closed")
        
    @classmethod
    def get_status(cls) -> dict:
        """Get status of all circuit breakers for monitoring"""
        return {
            name: {
                'state': cb.state.name,
                'failure_count': cb.failure_count,
                'failure_threshold': cb.failure_threshold,
                'recovery_timeout': cb.recovery_timeout,
                'last_failure_time': cb.last_failure_time
            }
            for name, cb in cls._instances.items()
        }

class CircuitBreakerError(Exception):
    """Exception raised when circuit is open"""
    pass