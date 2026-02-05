# models/lease.py
from sqlalchemy import Column, Integer, String, Numeric, Date, Boolean, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from .base import Base


class Lease(Base):
     """
     Lease model - rental agreements between tenants and properties/units.
     Maps to existing 'leases' table in the database.
     """
     __tablename__ = "leases"

     id = Column(Integer, primary_key=True, autoincrement=True)
     property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
     property_unit_id = Column(Integer, ForeignKey("property_units.id"), nullable=True)
     tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False)
     
     # Pricing
     rent_price = Column(Numeric(12, 2), nullable=False)
     deposit_price = Column(Numeric(12, 2), nullable=True)
     
     # Lease period
     start_date = Column(Date, nullable=False)
     end_date = Column(Date, nullable=False)
     
     # Terms
     tenancy_terms = Column(Text, nullable=True)
     lease_documents = Column(Text, nullable=True)  # Comma-separated file URLs
     
     # Utility bills
     bill_gas = Column(Boolean, default=False)
     bill_gas_amount = Column(Numeric(10, 2), nullable=True)
     bill_electricity = Column(Boolean, default=False)
     bill_electricity_amount = Column(Numeric(10, 2), nullable=True)
     bill_internet = Column(Boolean, default=False)
     bill_internet_amount = Column(Numeric(10, 2), nullable=True)
     bill_tax = Column(Boolean, default=False)
     bill_tax_amount = Column(Numeric(10, 2), nullable=True)
     
     # Timestamps
     created_at = Column(DateTime, server_default=func.now(), nullable=False)
     updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

     # Relationships
     property = relationship("Property", back_populates="leases")
     property_unit = relationship("PropertyUnit", back_populates="leases")
     tenant = relationship("Tenant", back_populates="leases")
     invoices = relationship("Invoice", back_populates="lease", cascade="all, delete-orphan")
     
     def __repr__(self):
          return f"<Lease(id={self.id}, tenant_id={self.tenant_id}, property_id={self.property_id})>"
