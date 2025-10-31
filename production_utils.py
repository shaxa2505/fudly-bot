"""
Enhanced security and reliability features for production deployment.
"""
import asyncio
import functools
import time
from typing import Callable, Any, Optional
from logging_config import logger


def retry_on_failure(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Decorator to retry failed operations with exponential backoff."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(f"Function {func.__name__} failed after {max_retries} retries: {e}")
                        raise e
                    
                    logger.warning(f"Function {func.__name__} failed (attempt {attempt + 1}), retrying in {current_delay}s: {e}")
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
            
            raise last_exception
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(f"Function {func.__name__} failed after {max_retries} retries: {e}")
                        raise e
                    
                    logger.warning(f"Function {func.__name__} failed (attempt {attempt + 1}), retrying in {current_delay}s: {e}")
                    time.sleep(current_delay)
                    current_delay *= backoff
            
            raise last_exception
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def circuit_breaker(failure_threshold: int = 5, recovery_timeout: int = 60):
    """Circuit breaker pattern to prevent cascade failures."""
    def decorator(func: Callable) -> Callable:
        func._failures = 0
        func._last_failure = 0
        func._state = 'closed'  # closed, open, half-open
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            now = time.time()
            
            # Check if we should attempt recovery
            if func._state == 'open' and now - func._last_failure > recovery_timeout:
                func._state = 'half-open'
                logger.info(f"Circuit breaker for {func.__name__} entering half-open state")
            
            # Reject calls in open state
            if func._state == 'open':
                raise Exception(f"Circuit breaker is open for {func.__name__}")
            
            try:
                result = await func(*args, **kwargs)
                
                # Reset on success
                if func._state == 'half-open':
                    func._state = 'closed'
                    func._failures = 0
                    logger.info(f"Circuit breaker for {func.__name__} closed (recovered)")
                
                return result
                
            except Exception as e:
                func._failures += 1
                func._last_failure = now
                
                if func._failures >= failure_threshold:
                    func._state = 'open'
                    logger.error(f"Circuit breaker opened for {func.__name__} after {func._failures} failures")
                
                raise e
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            now = time.time()
            
            if func._state == 'open' and now - func._last_failure > recovery_timeout:
                func._state = 'half-open'
            
            if func._state == 'open':
                raise Exception(f"Circuit breaker is open for {func.__name__}")
            
            try:
                result = func(*args, **kwargs)
                if func._state == 'half-open':
                    func._state = 'closed'
                    func._failures = 0
                return result
            except Exception as e:
                func._failures += 1
                func._last_failure = now
                if func._failures >= failure_threshold:
                    func._state = 'open'
                raise e
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


class HealthChecker:
    """Health monitoring for system components."""
    
    def __init__(self):
        self.components = {}
        self.last_check = {}
    
    def register_component(self, name: str, check_func: Callable, interval: int = 60):
        """Register a component for health monitoring."""
        self.components[name] = {
            'check_func': check_func,
            'interval': interval,
            'status': 'unknown',
            'last_error': None
        }
    
    async def check_health(self, component: Optional[str] = None) -> dict:
        """Check health of specific component or all components."""
        now = time.time()
        results = {}
        
        components_to_check = [component] if component else self.components.keys()
        
        for name in components_to_check:
            if name not in self.components:
                continue
                
            comp = self.components[name]
            
            # Skip if checked recently
            if name in self.last_check and now - self.last_check[name] < comp['interval']:
                results[name] = {
                    'status': comp['status'],
                    'cached': True
                }
                continue
            
            try:
                if asyncio.iscoroutinefunction(comp['check_func']):
                    await comp['check_func']()
                else:
                    comp['check_func']()
                
                comp['status'] = 'healthy'
                comp['last_error'] = None
                results[name] = {'status': 'healthy', 'cached': False}
                
            except Exception as e:
                comp['status'] = 'unhealthy'
                comp['last_error'] = str(e)
                results[name] = {'status': 'unhealthy', 'error': str(e), 'cached': False}
                logger.error(f"Health check failed for {name}: {e}")
            
            self.last_check[name] = now
        
        return results
    
    def get_overall_status(self) -> str:
        """Get overall system health status."""
        if not self.components:
            return 'unknown'
        
        statuses = [comp['status'] for comp in self.components.values()]
        
        if all(s == 'healthy' for s in statuses):
            return 'healthy'
        elif any(s == 'unhealthy' for s in statuses):
            return 'degraded'
        else:
            return 'unknown'


def graceful_shutdown(func: Callable) -> Callable:
    """Decorator to handle graceful shutdown of async operations."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError:
            logger.info(f"Graceful shutdown of {func.__name__}")
            # Perform cleanup here if needed
            raise
        except Exception as e:
            logger.error(f"Error during shutdown of {func.__name__}: {e}")
            raise
    return wrapper


# Global health checker instance
health_checker = HealthChecker()


def validate_production_config():
    """Validate that all required production configurations are set."""
    import os
    
    required_vars = ['TELEGRAM_BOT_TOKEN', 'ADMIN_ID']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    # Validate token format
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token or ':' not in token or len(token) < 45:
        raise ValueError("Invalid TELEGRAM_BOT_TOKEN format")
    
    # Validate admin ID
    try:
        admin_id = int(os.getenv('ADMIN_ID', 0))
        if admin_id <= 0:
            raise ValueError("ADMIN_ID must be a positive integer")
    except ValueError:
        raise ValueError("ADMIN_ID must be a valid integer")
    
    logger.info("Production configuration validated successfully")