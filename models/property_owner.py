# models/property_owner.py
"""
PropertyOwner model - links users with role 'owner' to their owner profile.
Used for role-based access: owners can view invoices for their properties.
"""
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base


class PropertyOwner(Base):
     """
     Property owner profile - maps to existing 'property_owners' table.
     """
     __tablename__ = "property_owners"

     owner_id = Column(Integer, primary_key=True, autoincrement=True)
     user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

     # Relationships (minimal for access control)
     # property_owners table has more columns; we only need owner_id/user_id for RBAC
     # Properties link via Property.registered_owner -> owner_id

     def __repr__(self):
          return f"<PropertyOwner(owner_id={self.owner_id}, user_id={self.user_id})>"
