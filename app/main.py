from fastapi import FastAPI

app = FastAPI(
    title="Mental Health Screening API",
    description="Backend API for the school mental-health screening system",
    version="1.0.0"
)

@app.get("/")
def home():
    return {"message": "Mental Health Screening API is running"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}