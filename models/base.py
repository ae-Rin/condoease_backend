# models/base.py
from sqlalchemy.orm import DeclarativeBase, declared_attr
from sqlalchemy import Column, DateTime, func


class Base(DeclarativeBase):
     """
     Base class for all SQLAlchemy models.
     Provides common configuration and mixins.
     """

     @declared_attr.directive
     def __tablename__(cls) -> str:
          """
          Automatically generate table name from class name.
          Example: PropertyUnit -> property_units
          """
          import re
          name = re.sub(r'(?<!^)(?=[A-Z])', '_', cls.__name__).lower()
          # Pluralize (simple version)
          if name.endswith('y'):
               return name[:-1] + 'ies'
          elif name.endswith('s'):
               return name + 'es'
          return name + 's'
