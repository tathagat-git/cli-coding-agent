"""
Todo Backend Application
A simple REST API for managing todos using FastAPI.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import todo_routes

app = FastAPI(
    title="Todo API",
    description="A simple REST API for managing todos",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(todo_routes.router)


@app.get("/")
async def root():
    """Root endpoint that returns API information."""
    return {
        "message": "Welcome to Todo API",
        "version": "1.0.0",
        "endpoints": {
            "docs": "/docs",
            "redoc": "/redoc",
            "todos": "/todos"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
