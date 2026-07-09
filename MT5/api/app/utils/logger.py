import logging
import sys
from app.utils.config import settings

class LoggerInstance:
    def __init__(self, name="app"):
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        log_file = "api.log"

        self.logger = logging.getLogger(name)
        self.logger.setLevel(
            getattr(logging, settings.env.LOG_LEVEL.upper(), logging.INFO)
        )

        if not self.logger.handlers:
            formatter = logging.Formatter(log_format)

            # Console handler
            ch = logging.StreamHandler(sys.stdout)
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)

            # File handler
            log_dir = settings.logs_dir
            fh = logging.FileHandler(log_dir / log_file)
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)

    def get_logger(self):
        return self.logger

logger_instance = LoggerInstance()
