#!/usr/bin/env python3
"""
Otto BGP WebUI Adapter - Minimal entry point

This file serves as the entry point for the WebUI service.
All application logic has been moved to webui.app and webui.core modules.
"""
from webui.app import app

if __name__ == "__main__":
    import uvicorn
    import ssl
    import os
    from pathlib import Path
    
    # SSL Configuration
    cert_path = Path("/etc/otto-bgp/certs/otto-bgp.crt")
    key_path = Path("/etc/otto-bgp/certs/otto-bgp.key")
    
    ssl_context = None
    if cert_path.exists() and key_path.exists():
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(str(cert_path), str(key_path))
    
    # Run server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8443,
        ssl_keyfile=str(key_path) if key_path.exists() else None,
        ssl_certfile=str(cert_path) if cert_path.exists() else None,
        log_level=os.getenv("OTTO_WEBUI_LOG_LEVEL", "info").lower()
    )