"""Database exception definitions"""


class DatabaseError(Exception):
    """Base database exception"""
    pass


class SchemaError(DatabaseError):
    """Schema initialization or migration error"""
    pass


class OverrideError(DatabaseError):
    """RPKI override operation error"""
    pass
