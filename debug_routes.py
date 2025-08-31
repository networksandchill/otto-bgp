#!/usr/bin/env python3
"""Debug FastAPI routes to find conflicts"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Mock settings to avoid needing full env
import webui.settings as settings
settings.CONFIG_DIR = "/tmp"
settings.DATA_DIR = "/tmp"
settings.WEBUI_ROOT = "/tmp"
settings.USERS_PATH = "/tmp/users.json"
settings.CONFIG_PATH = "/tmp/config.json"
settings.SETUP_TOKEN_PATH = "/tmp/setup_token"
settings.JWT_SECRET_PATH = "/tmp/jwt_secret"

from webui.webui_adapter import app

print("Analyzing FastAPI routes...")
print("=" * 60)

# Get all routes
routes = []
for route in app.routes:
    if hasattr(route, 'path') and hasattr(route, 'methods'):
        for method in route.methods:
            routes.append((method, route.path, route.name if hasattr(route, 'name') else 'unknown'))

# Sort by path, then method
routes.sort(key=lambda x: (x[1], x[0]))

# Look for /api/devices routes
print("\nDevice-related routes:")
print("-" * 40)
for method, path, name in routes:
    if 'devices' in path.lower():
        print(f"{method:8} {path:40} -> {name}")

print("\n\nAll API routes:")
print("-" * 40)
for method, path, name in routes:
    if path.startswith('/api'):
        print(f"{method:8} {path:40} -> {name}")