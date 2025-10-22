from fastapi import FastAPI
from app.routes import chat, health

app = FastAPI(title="ChatBot API")

# Include routers
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(health.router, prefix="/health", tags=["health"])

@app.get("/")
def root():
    return {"message": "Server is running"}
