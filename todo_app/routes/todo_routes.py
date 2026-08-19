"""
API routes for Todo items.
"""

from fastapi import APIRouter, HTTPException, status
from typing import List
from ..schemas.todo import Todo, TodoCreate, TodoUpdate, TodoResponse, TodoListResponse
from ..storage.todo_storage import (
    get_all_todos,
    get_todo_by_id,
    create_todo,
    update_todo,
    delete_todo
)

router = APIRouter(
    prefix="/todos",
    tags=["todos"]
)


@router.get("/", response_model=TodoListResponse)
async def list_todos(skip: int = 0, limit: int = 100):
    """
    Retrieve a list of all todos.
    
    - **skip**: Number of items to skip (for pagination)
    - **limit**: Maximum number of items to return (for pagination)
    """
    todos = get_all_todos()
    # Apply pagination
    paginated_todos = todos[skip:skip + limit]
    return {
        "success": True,
        "message": f"Retrieved {len(paginated_todos)} todo(s)",
        "data": paginated_todos,
        "count": len(paginated_todos)
    }


@router.get("/{todo_id}", response_model=TodoResponse)
async def get_todo(todo_id: int):
    """
    Retrieve a specific todo by its ID.
    
    - **todo_id**: The unique identifier of the todo item
    """
    todo = get_todo_by_id(todo_id)
    if not todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Todo with ID {todo_id} not found"
        )
    return {
        "success": True,
        "message": "Todo retrieved successfully",
        "data": todo
    }


@router.post("/", response_model=TodoResponse, status_code=status.HTTP_201_CREATED)
async def add_todo(todo: TodoCreate):
    """
    Create a new todo item.
    
    - **todo**: Todo creation data including title, description, and completed status
    """
    new_todo = create_todo(
        title=todo.title,
        description=todo.description,
        completed=todo.completed
    )
    return {
        "success": True,
        "message": "Todo created successfully",
        "data": new_todo
    }


@router.put("/{todo_id}", response_model=TodoResponse)
async def edit_todo(todo_id: int, todo: TodoUpdate):
    """
    Update an existing todo item.
    
    - **todo_id**: The unique identifier of the todo item
    - **todo**: Todo update data (all fields are optional)
    """
    updated_todo = update_todo(
        todo_id=todo_id,
        title=todo.title,
        description=todo.description,
        completed=todo.completed
    )
    if not updated_todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Todo with ID {todo_id} not found"
        )
    return {
        "success": True,
        "message": "Todo updated successfully",
        "data": updated_todo
    }


@router.patch("/{todo_id}", response_model=TodoResponse)
async def patch_todo(todo_id: int, todo: TodoUpdate):
    """
    Partially update a todo item.
    
    - **todo_id**: The unique identifier of the todo item
    - **todo**: Todo update data (all fields are optional)
    """
    updated_todo = update_todo(
        todo_id=todo_id,
        title=todo.title,
        description=todo.description,
        completed=todo.completed
    )
    if not updated_todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Todo with ID {todo_id} not found"
        )
    return {
        "success": True,
        "message": "Todo updated successfully",
        "data": updated_todo
    }


@router.delete("/{todo_id}", response_model=TodoResponse)
async def remove_todo(todo_id: int):
    """
    Delete a todo item.
    
    - **todo_id**: The unique identifier of the todo item
    """
    success = delete_todo(todo_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Todo with ID {todo_id} not found"
        )
    return {
        "success": True,
        "message": "Todo deleted successfully",
        "data": None
    }
