from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import Config
from models.auth import *
from routes.auth_routes import router as auth_router
from routes.integration_routes import router as integration_router
from services.keycloak_service import KeycloakService

# Initialize FastAPI app
app = FastAPI(title="MedApp Auth Service", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Keycloak service
keycloak_service = KeycloakService()


# Health check endpoint
@app.get("/health", response_model=HealthCheckResponse)
def health_check():
    return {"status": "healthy", "service": "auth-service"}


# Include the routers
app.include_router(auth_router)
app.include_router(integration_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host=Config.HOST, port=Config.PORT, reload=True, log_level="debug")
