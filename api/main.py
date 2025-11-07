"""
FastAPI Backend for Nordic Privacy AI
Provides endpoints for AI Governance analysis and data cleaning
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from api.routers import analyze, clean, discovery, detect_pii

# Create FastAPI app
app = FastAPI(
    title="Nordic Privacy AI API",
    description="AI-powered GDPR compliance, bias detection, and risk analysis",
    version="1.0.0"
)

# CORS configuration for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount reports directory for file downloads
reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")
os.makedirs(reports_dir, exist_ok=True)
app.mount("/reports", StaticFiles(directory=reports_dir), name="reports")

# Include routers
app.include_router(analyze.router, prefix="/api", tags=["AI Governance"])
app.include_router(clean.router, prefix="/api", tags=["Data Cleaning"])
app.include_router(detect_pii.router, prefix="/api", tags=["PII Detection"])
app.include_router(discovery.router, prefix="/api", tags=["Discover sources"])

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Nordic Privacy AI API",
        "version": "1.0.0",
        "endpoints": {
            "analyze": "/api/analyze",
            "clean": "/api/clean",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if cuda_available else None
    except:
        cuda_available = False
        gpu_name = None
    
    return {
        "status": "healthy",
        "gpu_acceleration": {
            "available": cuda_available,
            "device": gpu_name or "CPU"
        }
    }
