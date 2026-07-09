import logging
from typing import Optional
from fastapi import Depends, HTTPException, Header
from fastapi.security import APIKeyHeader
from starlette import status

from app.utils.config import settings

logger = logging.getLogger(__name__)

# Depend on the X-API-Key header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(
    api_key: Optional[str] = Depends(api_key_header),
    mt5_login: Optional[int] = Header(None, alias="X-MT5-Login"),
    mt5_password: Optional[str] = Header(None, alias="X-MT5-Password"),
    mt5_server: Optional[str] = Header(None, alias="X-MT5-Server")
):
    """
    Validates the provided API Key against the deterministic key from API_KEY_SEED.
    Also extracts MT5 credentials from headers.
    """
    generated_key = settings.api_key
    
    # Check if a seed is set globally
    if generated_key:
        if not api_key or api_key != generated_key:
            logger.warning(f"Unauthorized API access attempt with key: {api_key}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API Key",
            )

    return {
        "api_key": api_key,
        "mt5_login": mt5_login,
        "mt5_password": mt5_password,
        "mt5_server": mt5_server
    }