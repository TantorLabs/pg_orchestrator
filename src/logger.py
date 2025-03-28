import logging
import os
from datetime import datetime
import colorlog

def setup_logging(timestamp):
    logs_directory = "logs"
    os.makedirs(logs_directory, exist_ok=True)
    logfile_name = f"{logs_directory}/log_{timestamp}.txt"

    logger = logging.getLogger("pg_orchestartor")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    file_handler = logging.FileHandler(logfile_name)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    color_formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
        datefmt=None,
        reset=True,
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'yellow',
            'WARNING': 'bold_yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        },
        secondary_log_colors={},
        style='%'
    )
    stream_handler.setFormatter(color_formatter)
    logger.addHandler(stream_handler)

    return logger
TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
logger = setup_logging(TIMESTAMP)