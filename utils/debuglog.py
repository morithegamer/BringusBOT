from datetime import datetime
import os
import sys

LOG_TO_FILE = True
LOG_FILE_DIR = "logs"
LOG_FILE_NAME = "debug.log"
ENABLE_LOGGING = True

def _get_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _get_log_path():
    os.makedirs(LOG_FILE_DIR, exist_ok=True)
    return os.path.join(LOG_FILE_DIR, LOG_FILE_NAME)

def log(section: str, message: str, level: str = "INFO"):
    if not ENABLE_LOGGING:
        return

    timestamp = _get_timestamp()
    section = section.upper()
    level = level.upper()
    output = f"[{timestamp}] [{section}] [{level}] {message}"

    # Print to console and flush (Docker-friendly)
    print(output, flush=True)

    # Optionally write to file
    if LOG_TO_FILE:
        try:
            with open(_get_log_path(), "a", encoding="utf-8") as f:
                f.write(output + "\n")
        except Exception as e:
            print(f"[{timestamp}] [LOGGER] [ERROR] Failed to write to log file: {e}", flush=True)

    return output