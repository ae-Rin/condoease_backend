# models/tenant.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from .base import Base


class Tenant(Base):
     """
     Tenant model - extended profile for users with role='tenant'.
     Maps to existing 'tenants' table in the database.
     """
     __tablename__ = "tenants"

     tenant_id = Column(Integer, primary_key=True, autoincrement=True)
     user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
     
     # Personal info
     first_name = Column(String(100), nullable=False)
     last_name = Column(String(100), nullable=False)
     email = Column(String(255), nullable=False)
     contact_number = Column(String(50), nullable=True)
     
     # Address
     street = Column(String(255), nullable=True)
     barangay = Column(String(100), nullable=True)
     city = Column(String(100), nullable=True)
     province = Column(String(100), nullable=True)
     
     # ID verification
     id_type = Column(String(100), nullable=True)
     id_number = Column(String(100), nullable=True)
     id_document_url = Column(String(500), nullable=True)
     
     # Occupation
     occupation_status = Column(String(100), nullable=True)
     occupation_place = Column(String(255), nullable=True)
     
     # Emergency contact
     emergency_contact_name = Column(String(200), nullable=True)
     emergency_contact_number = Column(String(50), nullable=True)
     
     # Status
     status = Column(String(50), default="pending", nullable=False)  # pending, approved, denied
     admin_comment = Column(String(500), nullable=True)
     
     # Timestamps
     created_at = Column(DateTime, server_default=func.now(), nullable=False)
     updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

     # Relationships
     user = relationship("User", back_populates="tenant")
     leases = relationship("Lease", back_populates="tenant")
     invoices = relationship("Invoice", back_populates="tenant")
     
     def __repr__(self):
          return f"<Tenant(tenant_id={self.tenant_id}, name='{self.first_name} {self.last_name}')>"
