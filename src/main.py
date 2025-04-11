"""
Main FastAPI application module.

This module sets up the FastAPI application with all routes and middleware.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .auth.routes import auth_router, RateLimitMiddleware

# Create FastAPI app
app = FastAPI(
    title="Google Ad Manager Autonomous System",
    description="A comprehensive SOAP API integration layer for Google Ad Manager",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with actual frontend origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware)

# Include routers
app.include_router(auth_router)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"} 