"""Utility functions for working with database results (dict or tuple format)."""
from typing import Any, Union


def safe_get(data: Union[dict, tuple, list], key: Union[str, int], default: Any = None) -> Any:
    """
    Safely get value from dict (by key) or tuple/list (by index).
    
    Works with both PostgreSQL (dict) and SQLite (tuple) formats.
    
    Args:
        data: Dictionary or tuple/list
        key: String key for dict, integer index for tuple/list
        default: Default value if key/index not found
        
    Returns:
        Value from data or default
        
    Examples:
        >>> safe_get({'name': 'Test'}, 'name')
        'Test'
        >>> safe_get(('Test', 'City'), 0)
        'Test'
        >>> safe_get({'name': 'Test'}, 'missing', 'N/A')
        'N/A'
    """
    if isinstance(data, dict):
        # PostgreSQL returns dicts
        if isinstance(key, str):
            return data.get(key, default)
        # If key is int but data is dict, try to get by numeric index from values
        elif isinstance(key, int) and key >= 0:
            values = list(data.values())
            return values[key] if key < len(values) else default
    elif isinstance(data, (tuple, list)):
        # SQLite returns tuples
        if isinstance(key, int):
            return data[key] if 0 <= key < len(data) else default
        # If key is string but data is tuple, cannot access by key
        return default
    return default
