from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database.base import Base

class Document(Base):
    __tablename__ = 'documents'

    id = Column(String(36), primary_key=True)  # UUID
    title = Column(String(255), nullable=False)
    source_file = Column(String(512), nullable=False)
    author = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    structure_blueprint = Column(Text, nullable=True)  # JSON string representing global structure blueprint

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
