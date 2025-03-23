import logging
import time
import functools
import json
import os
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast

# Set up debug directory
DEBUG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "debug_logs")
os.makedirs(DEBUG_DIR, exist_ok=True)

# Type variable for function decorators
F = TypeVar('F', bound=Callable[..., Any])

def time_function(func: F) -> F:
    """
    Decorator to measure and log function execution time
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger = logging.getLogger("research_bot")
        start_time = time.time()
        
        result = func(*args, **kwargs)
        
        elapsed = time.time() - start_time
        logger.debug(f"Function {func.__name__} completed in {elapsed:.2f}s")
        
        return result
    
    return cast(F, wrapper)

def time_async_function(func: F) -> F:
    """
    Decorator to measure and log async function execution time
    """
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger = logging.getLogger("research_bot")
        start_time = time.time()
        
        result = await func(*args, **kwargs)
        
        elapsed = time.time() - start_time
        logger.debug(f"Async function {func.__name__} completed in {elapsed:.2f}s")
        
        return result
    
    return cast(F, wrapper)

def log_agent_inputs(func: F) -> F:
    """
    Decorator to log inputs being sent to agent functions
    """
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger = logging.getLogger("research_bot")
        
        # Find the input argument - typically the second arg after 'self'
        input_value = args[1] if len(args) > 1 else kwargs.get('input', None)
        
        if input_value:
            # Create a log filename based on function name and timestamp
            timestamp = int(time.time())
            log_filename = f"{func.__name__}_{timestamp}_input.txt"
            log_path = os.path.join(DEBUG_DIR, log_filename)
            
            # Save input to file
            with open(log_path, 'w') as f:
                f.write(str(input_value))
            
            logger.debug(f"Logged agent input to {log_filename}")
        
        result = await func(*args, **kwargs)
        
        # If result has a final_output property, log that too
        if hasattr(result, 'final_output'):
            output_filename = f"{func.__name__}_{timestamp}_output.txt"
            output_path = os.path.join(DEBUG_DIR, output_filename)
            
            with open(output_path, 'w') as f:
                f.write(str(result.final_output))
            
            logger.debug(f"Logged agent output to {output_filename}")
        
        return result
    
    return cast(F, wrapper)

def dump_object(obj: Any, name: str) -> None:
    """
    Utility to dump any object to a JSON file for debugging
    """
    logger = logging.getLogger("research_bot")
    timestamp = int(time.time())
    
    filename = f"{name}_{timestamp}.json"
    path = os.path.join(DEBUG_DIR, filename)
    
    try:
        # Try to convert to dict if possible
        if hasattr(obj, "__dict__"):
            data = obj.__dict__
        elif hasattr(obj, "to_dict"):
            data = obj.to_dict()
        else:
            data = obj
            
        with open(path, 'w') as f:
            json.dump(data, f, default=str, indent=2)
            
        logger.debug(f"Dumped {name} object to {filename}")
    except Exception as e:
        logger.error(f"Failed to dump {name} object: {str(e)}")

def capture_exception(e: Exception, context: str = "") -> None:
    """
    Utility to log exceptions with context
    """
    logger = logging.getLogger("research_bot")
    timestamp = int(time.time())
    
    filename = f"exception_{timestamp}.txt"
    path = os.path.join(DEBUG_DIR, filename)
    
    with open(path, 'w') as f:
        f.write(f"Context: {context}\n\n")
        f.write(f"Exception type: {type(e).__name__}\n")
        f.write(f"Exception message: {str(e)}\n\n")
        f.write("Traceback:\n")
        import traceback
        f.write(traceback.format_exc())
    
    logger.error(f"Exception in {context}. Details logged to {filename}") 