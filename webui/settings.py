"""
Otto BGP WebUI Settings
Centralized configuration paths and environment variables
"""

import os
from pathlib import Path

# Base directory paths
CONFIG_DIR = Path(os.getenv('OTTO_BGP_CONFIG_DIR', '/etc/otto-bgp'))
DATA_DIR = Path(os.getenv('OTTO_BGP_DATA_DIR', '/var/lib/otto-bgp'))
WEBUI_ROOT = Path(os.getenv('OTTO_WEBUI_ROOT', '/usr/local/share/otto-bgp/webui'))

# Configuration files
USERS_PATH = CONFIG_DIR / 'users.json'
CONFIG_PATH = CONFIG_DIR / 'config.json'
SETUP_TOKEN_PATH = CONFIG_DIR / '.setup_token'
JWT_SECRET_PATH = CONFIG_DIR / '.jwt_secret'

# Environment configuration
OTTO_DEV_MODE = os.getenv('OTTO_DEV_MODE', 'false').lower() == 'true'
OTTO_WEBUI_LOG_LEVEL = os.getenv('OTTO_WEBUI_LOG_LEVEL', 'INFO').upper()
OTTO_WEBUI_ENABLE_SERVICE_CONTROL = os.getenv('OTTO_WEBUI_ENABLE_SERVICE_CONTROL', 'false').lower() == 'true'

