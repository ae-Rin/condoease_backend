# models/property_unit.py
from sqlalchemy import Column, Integer, String, Numeric, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from .base import Base


class PropertyUnit(Base):
     """
     PropertyUnit model - individual units within a property.
     Maps to existing 'property_units' table in the database.
     """
     __tablename__ = "property_units"

     id = Column(Integer, primary_key=True, autoincrement=True)
     property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
     
     unit_type = Column(String(100), nullable=True)
     unit_number = Column(String(50), nullable=False)
     commission_percentage = Column(Numeric(5, 2), nullable=True)
     rent_price = Column(Numeric(12, 2), nullable=True)
     deposit_price = Column(Numeric(12, 2), nullable=True)
     floor = Column(String(20), nullable=True)
     size = Column(Numeric(10, 2), nullable=True)
     description = Column(Text, nullable=True)
     status = Column(String(50), default="vacant", nullable=False)  # vacant, occupied
     
     # Timestamps
     created_at = Column(DateTime, server_default=func.now(), nullable=False)
     updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

     # Relationships
     property = relationship("Property", back_populates="property_units")
     leases = relationship("Lease", back_populates="property_unit")
     
     def __repr__(self):
          return f"<PropertyUnit(id={self.id}, unit_number='{self.unit_number}', status='{self.status}')>"
