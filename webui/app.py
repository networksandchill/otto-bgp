import logging
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from webui.settings import WEBUI_ROOT, OTTO_WEBUI_LOG_LEVEL
from webui.core.audit import setup_audit_logging
from webui.core.security import needs_setup

# Setup logging
logger = logging.getLogger("otto.webui")
log_level = getattr(logging, OTTO_WEBUI_LOG_LEVEL, logging.INFO)
logger.setLevel(log_level)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    handler.setLevel(log_level)
    logger.addHandler(handler)

# Initialize audit logger
audit_logger = setup_audit_logging()

def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    app = FastAPI(
        title="Otto BGP WebUI",
        description="Web interface for Otto BGP management",
        version="0.3.2",
        docs_url=None,  # Disable auto docs in production
        redoc_url=None
    )
    
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
    
    @app.middleware("http")
    async def setup_gate(request: Request, call_next):
        """Gate non-setup endpoints during setup mode (match current behavior)"""
        path = request.url.path
        if (
            path.startswith('/api/setup') or
            path.startswith('/assets') or
            path.startswith('/healthz') or
            path == '/' or
            path == '/setup'
        ):
            return await call_next(request)

        state = needs_setup()
        if state['needs_setup']:
            return JSONResponse({'error': 'setup_required'}, status_code=403)

        return await call_next(request)
    
    # Mount static assets  
    static_dir = WEBUI_ROOT / "static"
    if not static_dir.exists():
        # Fallback to direct webui directory if static subdirectory doesn't exist
        static_dir = WEBUI_ROOT
    
    if (static_dir / "assets").exists():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
    
    # App-level routes
    @app.get("/")
    async def serve_index():
        # Try static subdirectory first, then direct webui directory
        static_dir = WEBUI_ROOT / "static"
        if not static_dir.exists():
            static_dir = WEBUI_ROOT
            
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return HTMLResponse("<h1>Otto BGP WebUI</h1><p>Frontend assets not found</p>")
    
    @app.get("/healthz")
    async def healthz():
        return JSONResponse({"status": "ok", "timestamp": datetime.utcnow().isoformat()})
    
    # Include routers
    from webui.api import (
        auth, setup, profile, users, devices, config, reports, systemd,
        rpki, rpki_overrides, logs, irr_proxy, ssh, pipeline
    )

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(setup.router, prefix="/api/setup", tags=["setup"])
    app.include_router(profile.router, prefix="/api/profile", tags=["profile"])
    app.include_router(users.router, prefix="/api/users", tags=["users"])
    app.include_router(devices.router, prefix="/api/devices", tags=["devices"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
    app.include_router(systemd.router, prefix="/api/systemd", tags=["systemd"])
    app.include_router(rpki.router, prefix="/api/rpki", tags=["rpki"])
    app.include_router(
        rpki_overrides.router,
        prefix="/api/rpki-overrides",
        tags=["rpki-overrides"]
    )
    app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
    app.include_router(irr_proxy.router, prefix="/api/irr-proxy", tags=["irr-proxy"])
    app.include_router(ssh.router, prefix="/api/ssh", tags=["ssh"])
    app.include_router(pipeline.router, prefix="/api/pipeline", tags=["pipeline"])

    # Catch-all route - MUST BE LAST
    @app.get("/{path:path}")
    async def catch_all(path: str):
        """Catch-all route for client-side routing"""
        # Try static subdirectory first, then direct webui directory
        static_dir = WEBUI_ROOT / "static"
        if not static_dir.exists():
            static_dir = WEBUI_ROOT
            
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return HTMLResponse("<h1>Otto BGP WebUI</h1><p>Frontend assets not found</p>")
    
    return app

# Create app instance for import compatibility
app = create_app()