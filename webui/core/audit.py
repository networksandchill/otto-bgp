import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from webui.settings import DATA_DIR


def setup_audit_logging():
    """Initialize audit logger with plain text formatter"""
    audit_logger = logging.getLogger("otto.audit")
    audit_logger.setLevel(logging.INFO)
    
    # Create logs directory under DATA_DIR
    log_dir = DATA_DIR / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as e:
        # In development, use a null handler if we can't create the directory
        logging.getLogger("otto.webui").warning(f"Cannot create log directory {log_dir}: {e}")
        if not audit_logger.handlers:
            audit_logger.addHandler(logging.NullHandler())
        return audit_logger
    
    # Check if handler already exists to avoid duplicates
    if not audit_logger.handlers:
        handler = TimedRotatingFileHandler(
            log_dir / "audit.log", when="midnight", interval=1, backupCount=90
        )
        
        class AuditFormatter(logging.Formatter):
            def format(self, record):
                timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                user = getattr(record, 'user', 'system')
                action = record.msg
                resource = getattr(record, 'resource', None)
                result = getattr(record, 'result', 'success')
                
                # Build message parts
                parts = [f"User: {user}", f"Action: {action}"]
                if resource:
                    parts.append(f"Resource: {resource}")
                parts.append(f"Result: {result}")
                
                return f"{timestamp} - AUDIT - {' | '.join(parts)}"
        
        handler.setFormatter(AuditFormatter())
        audit_logger.addHandler(handler)
    return audit_logger

# Initialize at module level
audit_logger = setup_audit_logging()


def audit_log(action: str, user: str = None, **kwargs):
    """Log an audit event"""
    audit_logger.info(action, extra={'user': user, **kwargs})
