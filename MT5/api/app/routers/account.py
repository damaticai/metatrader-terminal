from fastapi import APIRouter
from app.services.mt5_service import mt5_service
from app.services.connector import mt5_connector
from app.utils.constants import RETCODE_DESCRIPTIONS
from app.utils.exceptions import MT5ConnectionError

router = APIRouter(prefix="/account", tags=["Account"])


@router.get("/health")
def health():
    if mt5_connector._initialized:
        return {"status": "healthy", "mt5": "connected"}
    if mt5_connector._initializing:
        return {"status": "connecting", "mt5": "initializing"}
    return {"status": "unhealthy", "mt5": "disconnected"}


@router.get("/last_error")
def get_last_error():
    error = mt5_service.last_error()
    return {
        "error_code": error[0],
        "error_message": error[1],
        "description": RETCODE_DESCRIPTIONS.get(error[0], "Unknown error code")
    }


@router.get("/retcodes")
def get_retcodes():
    return RETCODE_DESCRIPTIONS
