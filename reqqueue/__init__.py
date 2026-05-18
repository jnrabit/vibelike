def __getattr__(name):
    """Lazy loading to avoid shadowing Python's built-in queue module."""
    if name == "RequestQueue":
        from .manager import RequestQueue
        return RequestQueue
    elif name == "QueueStatus":
        from .manager import QueueStatus
        return QueueStatus
    elif name == "ReminderManager":
        from .reminders import ReminderManager
        return ReminderManager
    elif name == "Reminder":
        from .reminders import Reminder
        return Reminder
    elif name == "HealthCheck":
        from .health import HealthCheck
        return HealthCheck
    elif name == "HealthStatus":
        from .health import HealthStatus
        return HealthStatus
    elif name == "RequestWorker":
        from .worker import RequestWorker
        return RequestWorker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["RequestQueue", "QueueStatus", "ReminderManager", "Reminder", "HealthCheck", "HealthStatus", "RequestWorker"]
