"""
In-memory storage for Todo items.
In a real application, this would be replaced with a database.
"""

from datetime import datetime
from typing import List, Optional
from ..models.todo import Todo

# In-memory storage
_todos: List[Todo] = []
_next_id: int = 1


def get_all_todos() -> List[Todo]:
    """Get all todo items."""
    return _todos.copy()


def get_todo_by_id(todo_id: int) -> Optional[Todo]:
    """Get a todo item by its ID."""
    for todo in _todos:
        if todo.id == todo_id:
            return todo
    return None


def create_todo(title: str, description: Optional[str], completed: bool) -> Todo:
    """Create a new todo item."""
    global _next_id
    now = datetime.now()
    todo = Todo(
        id=_next_id,
        title=title,
        description=description,
        completed=completed,
        created_at=now,
        updated_at=now
    )
    _todos.append(todo)
    _next_id += 1
    return todo


def update_todo(todo_id: int, title: Optional[str], description: Optional[str], completed: Optional[bool]) -> Optional[Todo]:
    """Update an existing todo item."""
    for i, todo in enumerate(_todos):
        if todo.id == todo_id:
            update_data = {}
            if title is not None:
                update_data["title"] = title
            if description is not None:
                update_data["description"] = description
            if completed is not None:
                update_data["completed"] = completed

            updated_todo = todo.model_copy(update=update_data)
            updated_todo.updated_at = datetime.now()
            _todos[i] = updated_todo
            return updated_todo
    return None


def delete_todo(todo_id: int) -> bool:
    """Delete a todo item by its ID."""
    for i, todo in enumerate(_todos):
        if todo.id == todo_id:
            _todos.pop(i)
            return True
    return False


def clear_all_todos() -> int:
    """Clear all todo items. Returns the number of deleted items."""
    global _todos, _next_id
    count = len(_todos)
    _todos = []
    _next_id = 1
    return count
