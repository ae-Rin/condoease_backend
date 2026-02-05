# models/property.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from .base import Base


class Property(Base):
     """
     Property model - represents a condo/apartment building.
     Maps to existing 'properties' table in the database.
     """
     __tablename__ = "properties"

     id = Column(Integer, primary_key=True, autoincrement=True)
     property_name = Column(String(255), nullable=False)
     registered_owner = Column(Integer, ForeignKey("property_owners.owner_id"), nullable=True)
     area_measurement = Column(String(100), nullable=True)
     description = Column(Text, nullable=True)
     
     # Address
     street = Column(String(255), nullable=True)
     barangay = Column(String(100), nullable=True)
     city = Column(String(100), nullable=True)
     province = Column(String(100), nullable=True)
     
     property_notes = Column(Text, nullable=True)
     units = Column(Integer, default=0, nullable=False)
     selected_features = Column(Text, nullable=True)  # JSON or comma-separated
     
     # Timestamps
     created_at = Column(DateTime, server_default=func.now(), nullable=False)
     updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

     # Relationships
     property_units = relationship("PropertyUnit", back_populates="property", cascade="all, delete-orphan")
     leases = relationship("Lease", back_populates="property")
     
     def __repr__(self):
          return f"<Property(id={self.id}, name='{self.property_name}')>"
