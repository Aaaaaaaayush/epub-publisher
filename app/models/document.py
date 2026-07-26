from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from app.database.base import Base

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)

    documents = relationship("Document", back_populates="owner", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = 'documents'

    id = Column(String(36), primary_key=True)  # UUID
    title = Column(String(255), nullable=False)
    source_file = Column(String(512), nullable=False)
    author = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    structure_blueprint = Column(Text, nullable=True)  # JSON string representing global structure blueprint
    owner_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    is_collaborative = Column(Boolean, default=False)

    # Relationships
    owner = relationship("User", back_populates="documents")
    # Relationship to sections: if a document is deleted, cascade delete all its sections
    sections = relationship("Section", back_populates="document", cascade="all, delete-orphan")


class Section(Base):
    __tablename__ = 'sections'

    id = Column(String(36), primary_key=True)  # UUID or stable hierarchy ID
    document_id = Column(String(36), ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    parent_id = Column(String(36), ForeignKey('sections.id', ondelete='SET NULL'), nullable=True)
    
    section_type = Column(String(50), nullable=False)  # 'book', 'chapter', 'topic', 'subtopic'
    level = Column(Integer, nullable=False)            # 0=Book, 1=Chapter, 2=Topic, 3=Subtopic
    position = Column(Integer, nullable=False)         # Ordering within parent
    title = Column(String(255), nullable=True)
    
    raw_markdown = Column(Text, nullable=True)
    formatted_markdown = Column(Text, nullable=True)
    validated_markdown = Column(Text, nullable=True)
    html_content = Column(Text, nullable=True)
    
    validation_status = Column(String(50), default="pending")  # 'pending', 'passed', 'failed'
    processing_status = Column(String(50), default="extracted") # 'extracted', 'split', 'formatted', 'validated', 'html_generated'
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="sections")
    
    # Self-referential relationship for parent-child section nesting
    parent = relationship("Section", remote_side=[id], back_populates="children")
    children = relationship("Section", back_populates="parent", cascade="all, delete-orphan")


class UserPermission(Base):
    __tablename__ = 'user_permissions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    document_id = Column(String(36), ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    section_id = Column(String(36), ForeignKey('sections.id', ondelete='CASCADE'), nullable=False)

    user = relationship("User")
    document = relationship("Document")
    section = relationship("Section")

class BookAccess(Base):
    __tablename__ = 'book_access'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    document_id = Column(String(36), ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)

    user = relationship("User")
    document = relationship("Document")
