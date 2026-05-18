"""Configuration management for Vibelike."""

import os
from pathlib import Path

# Get the root directory (vibelike project root)
ROOT_DIR = Path(__file__).parent

# Queue and logging paths
QUEUE_DB = Path(os.environ.get("VIBELIKE_QUEUE_DB", ROOT_DIR / "logs" / "queue.db"))
LOG_DB = Path(os.environ.get("VIBELIKE_LOG_DB", ROOT_DIR / "logs" / "execution.db"))
OSSIFIKAT_DB = Path(os.environ.get("VIBELIKE_OSSIFIKAT_DB", ROOT_DIR / "ossifikat" / "data" / "ossifikat.db"))

# Sandbox and tools paths
SANDBOX_BASE = Path(os.environ.get("VIBELIKE_SANDBOX_BASE", ROOT_DIR / "sandbox"))
TOOLS_DIR = Path(os.environ.get("VIBELIKE_TOOLS_DIR", ROOT_DIR / "tools"))
TOOLS_CACHE_DIR = Path(os.environ.get("VIBELIKE_TOOLS_CACHE_DIR", ROOT_DIR / "cache"))
RESULTS_DIR = Path(os.environ.get("VIBELIKE_RESULTS_DIR", ROOT_DIR / "logs" / "results"))

# Create directories if they don't exist
QUEUE_DB.parent.mkdir(parents=True, exist_ok=True)
LOG_DB.parent.mkdir(parents=True, exist_ok=True)
OSSIFIKAT_DB.parent.mkdir(parents=True, exist_ok=True)
SANDBOX_BASE.mkdir(parents=True, exist_ok=True)
TOOLS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Health check settings
HEALTH_CHECK_FILE = Path(os.environ.get("VIBELIKE_HEALTH_FILE", "/tmp/vibelike_queue_health"))
HEALTH_CHECK_MAX_AGE = int(os.environ.get("VIBELIKE_HEALTH_MAX_AGE", "30"))

# Worker settings
POLL_INTERVAL = float(os.environ.get("VIBELIKE_POLL_INTERVAL", "5.0"))
HEALTH_CHECK_INTERVAL = int(os.environ.get("VIBELIKE_HEALTH_CHECK_INTERVAL", "30"))

# Sandbox settings
SANDBOX_USER_UID = int(os.environ.get("VIBELIKE_SANDBOX_UID", "10000"))
SANDBOX_USER_GID = int(os.environ.get("VIBELIKE_SANDBOX_GID", "10000"))
SANDBOX_TIMEOUT = int(os.environ.get("VIBELIKE_SANDBOX_TIMEOUT", "300"))

# Ossifikat settings (optional)
OSSIFIKAT_ENABLED = os.environ.get("VIBELIKE_OSSIFIKAT_ENABLED", "true").lower() in ("true", "1", "yes")
