import logging
import logging.handlers
import os
from pathlib import Path
from typing import Optional
import json
from datetime import datetime
from functools import wraps
import time

# Create logs directory if it doesn't exist
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

# Configure logging
def setup_logging(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # File handler for all logs
    file_handler = logging.handlers.RotatingFileHandler(
        logs_dir / "validator.log",
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)

    # Error file handler
    error_handler = logging.handlers.RotatingFileHandler(
        logs_dir / "error.log",
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    error_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)

    return logger

# Metrics collection
class MetricsCollector:
    def __init__(self):
        self.metrics_file = logs_dir / "metrics.json"
        self.metrics = self._load_metrics()

    def _load_metrics(self):
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file) as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return self._create_default_metrics()
        return self._create_default_metrics()

    def _create_default_metrics(self):
        return {
            "api_calls": {},
            "token_creation": {
                "fungible": 0,
                "non_fungible": 0
            },
            "wallet_creation": 0,
            "errors": {},
            "response_times": []
        }

    def _save_metrics(self):
        with open(self.metrics_file, "w") as f:
            json.dump(self.metrics, f, indent=2)

    def record_api_call(self, endpoint: str):
        self.metrics["api_calls"][endpoint] = self.metrics["api_calls"].get(endpoint, 0) + 1
        self._save_metrics()

    def record_token_creation(self, token_type: str):
        self.metrics["token_creation"][token_type] += 1
        self._save_metrics()

    def record_wallet_creation(self):
        self.metrics["wallet_creation"] += 1
        self._save_metrics()

    def record_error(self, error_type: str):
        self.metrics["errors"][error_type] = self.metrics["errors"].get(error_type, 0) + 1
        self._save_metrics()

    def record_response_time(self, endpoint: str, time_ms: float):
        self.metrics["response_times"].append({
            "endpoint": endpoint,
            "time_ms": time_ms,
            "timestamp": datetime.utcnow().isoformat()
        })
        # Keep only last 1000 response times
        if len(self.metrics["response_times"]) > 1000:
            self.metrics["response_times"] = self.metrics["response_times"][-1000:]
        self._save_metrics()

# Create global instances
logger = setup_logging("validator")
metrics = MetricsCollector()

# Decorator for monitoring endpoints
def monitor_endpoint(endpoint_name: Optional[str] = None):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            endpoint = endpoint_name or func.__name__
            
            try:
                result = await func(*args, **kwargs)
                metrics.record_api_call(endpoint)
                return result
            except Exception as e:
                metrics.record_error(type(e).__name__)
                logger.error(f"Error in {endpoint}: {str(e)}")
                raise
            finally:
                end_time = time.time()
                response_time = (end_time - start_time) * 1000  # Convert to milliseconds
                metrics.record_response_time(endpoint, response_time)
        
        return wrapper
    return decorator 