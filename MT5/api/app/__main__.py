import uvicorn
from app.utils.config import settings
from app.utils.logger import logger_instance

logger = logger_instance.get_logger()

def main():
    logger.info(
        f"Starting {settings.env.API_NAME} on {settings.env.HOST}:{settings.env.PORT}"
    )
    uvicorn.run(
        "app.main:app",
        host=settings.env.HOST,
        port=settings.env.PORT,
        reload=False,  # uvicorn file watcher hangs under Wine
        log_level=settings.env.LOG_LEVEL.lower(),
    )

if __name__ == "__main__":
    main()