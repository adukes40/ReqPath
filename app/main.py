"""
Procurement Workflow API
Main application entry point
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time

from app.config import get_settings
from app.database import engine, Base
from app.routers import requests, documents, approvals, reports, users

settings = get_settings()


# =============================================================================
# LIFESPAN - Startup/Shutdown
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting Procurement API...")
    
    # Create database tables
    Base.metadata.create_all(bind=engine)
    print("Database tables created/verified")
    
    yield
    
    # Shutdown
    print("Shutting down...")


# =============================================================================
# APP INSTANCE
# =============================================================================

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    ## Procurement Workflow API
    
    A simple, fast API for managing procurement requests, approvals, and documents.
    
    ### Features
    - **Requests**: Create and manage procurement requests
    - **Line Items**: Track items being purchased
    - **Documents**: Upload quotes, invoices, POs
    - **Approvals**: Workflow for request approval
    - **Reports**: Spending and vendor analytics
    
    ### Authentication
    Pass your API key via:
    - Header: `X-API-Key: your-key`
    - Query: `?api_key=your-key`
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)


# =============================================================================
# MIDDLEWARE
# =============================================================================

# CORS - adjust origins for your environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        # Add your frontend URLs here
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(round(process_time * 1000, 2)) + "ms"
    return response


# =============================================================================
# EXCEPTION HANDLERS
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler"""
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "type": type(exc).__name__
        }
    )


# =============================================================================
# ROUTES
# =============================================================================

# Health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": settings.app_version}


# API info
@app.get("/", tags=["Info"])
async def root():
    """API information"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health"
    }


# Include routers
app.include_router(requests.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(documents.download_router, prefix="/api/v1")
app.include_router(approvals.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")


# =============================================================================
# DEV SERVER
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
