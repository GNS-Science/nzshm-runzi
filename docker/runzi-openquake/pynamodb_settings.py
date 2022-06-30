"""pynamodb_settings.

Default settings may be overridden by providing a Python module which exports the desired new values. Set the
PYNAMODB_CONFIG environment variable to an absolute path to this module or write it to /etc/pynamodb/
global_default_settings.py to have it automatically discovered.
"""

max_pool_connections = 10  # default 10
base_backoff_ms = 200  # default 25
max_retry_attempts = 8  # default 3
read_timeout_seconds = 30  # default 30
connect_timeout_seconds = 20  # default 15
