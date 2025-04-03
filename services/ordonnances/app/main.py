from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.ordonnance_routes import ordonnance_router

app = FastAPI(
    title="Ordonnances API", description="API pour la gestion des ordonnances médicales"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(ordonnance_router, prefix="/ordonnances")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
