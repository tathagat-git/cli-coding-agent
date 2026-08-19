"""
Data models for the Todo application.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class TodoBase(BaseModel):
    """Base model for Todo items."""
    title: str = Field(..., min_length=1, max_length=200, description="The title of the todo item")
    description: Optional[str] = Field(None, max_length=1000, description="Detailed description of the todo item")
    completed: bool = Field(default=False, description="Whether the todo item is completed")


class TodoCreate(TodoBase):
    """Model for creating a new Todo item."""
    pass


class TodoUpdate(BaseModel):
    """Model for updating an existing Todo item."""
    title: Optional[str] = Field(None, min_length=1, max_length=200, description="The title of the todo item")
    description: Optional[str] = Field(None, max_length=1000, description="Detailed description of the todo item")
    completed: Optional[bool] = Field(None, description="Whether the todo item is completed")


class TodoInDBBase(TodoBase):
    """Base model for Todo items in the database."""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Todo(TodoInDBBase):
    """Model for returning Todo items from the API."""
    pass
