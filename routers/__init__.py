# models/user.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from sqlalchemy.orm import relationship
from .base import Base


class User(Base):
     """
     User model - central authentication table.
     Maps to existing 'users' table in the database.
     """
     __tablename__ = "users"

     id = Column(Integer, primary_key=True, autoincrement=True)
     email = Column(String(255), unique=True, nullable=False, index=True)
     password = Column(String(255), nullable=False)
     first_name = Column(String(100), nullable=False)
     last_name = Column(String(100), nullable=False)
     role = Column(String(50), nullable=False)  # admin, manager, owner, tenant, agent
     avatar = Column(String(500), nullable=True)
     email_verified = Column(Boolean, default=False, nullable=False)
     is_active = Column(Boolean, default=False, nullable=False)
     pending_otp = Column(String(10), nullable=True)
     otp_expires_at = Column(DateTime, nullable=True)
     created_at = Column(DateTime, server_default=func.now(), nullable=False)

     # Relationships
     tenant = relationship("Tenant", back_populates="user", uselist=False)
     
     def __repr__(self):
          return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"
