"""Database persistence package introduced in Petshop API v0.6.0."""
from .base import Base
from .session import Database

__all__ = ['Base', 'Database']
