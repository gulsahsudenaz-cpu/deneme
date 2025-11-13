import time
import psutil
from datetime import datetime
from typing import Dict, Any, List
from collections import deque
from app.logger import logger

class SystemMonitor:
    """System monitoring utilities for health checks and metrics"""
    
    @staticmethod
    def get_system_metrics() -> Dict[str, Any]:
        """Get current system metrics"""
        try:
            cpu_percent = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_mb": memory.available // (1024 * 1024),
                "disk_percent": disk.percent,
                "disk_free_gb": disk.free // (1024 * 1024 * 1024),
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def check_system_health() -> Dict[str, Any]:
        """Check if system is healthy based on resource usage"""
        metrics = SystemMonitor.get_system_metrics()
        
        if "error" in metrics:
            return {"status": "error", "details": metrics}
        
        warnings = []
        
        # Check CPU usage
        if metrics["cpu_percent"] > 80:
            warnings.append(f"High CPU usage: {metrics['cpu_percent']}%")
        
        # Check memory usage
        if metrics["memory_percent"] > 85:
            warnings.append(f"High memory usage: {metrics['memory_percent']}%")
        
        # Check disk usage
        if metrics["disk_percent"] > 90:
            warnings.append(f"High disk usage: {metrics['disk_percent']}%")
        
        status = "warning" if warnings else "healthy"
        
        return {
            "status": status,
            "warnings": warnings,
            "metrics": metrics
        }

_background_errors = deque(maxlen=50)

def record_background_error(label: str, error: Exception | str) -> None:
    """Store background task errors for later inspection"""
    try:
        _background_errors.append({
            "label": label,
            "error": str(error),
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as exc:
        logger.error(f"Failed to record background error: {exc}")

def get_recent_background_errors(limit: int = 50) -> List[dict]:
    """Return recent background task errors"""
    if limit <= 0:
        return []
    return list(_background_errors)[-limit:]
