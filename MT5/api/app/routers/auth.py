from fastapi import APIRouter
from pydantic import BaseModel
from app.utils.config import settings
from app.services.connector import mt5_connector
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

class LoginRequest(BaseModel):
    login: int
    password: str
    server: str

@router.post("/login")
def login(request: LoginRequest):
    """
    Returns the API key for authenticated requests.
    MT5 account credentials are configured via environment variables
    and handled by the auto-login process at container startup.
    """
    mt5_connector.initialize()
    return {
        "message": "Login successful",
        "api_key": settings.api_key,
        "login": request.login,
        "server": request.server
    }
