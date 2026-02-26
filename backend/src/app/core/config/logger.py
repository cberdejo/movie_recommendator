import logging


def get_logger(name: str = "hybrid_rag_analysis") -> logging.Logger:
    """
    Creates and configures a logger instance with a specified name.
    This function sets up a logger with a default logging level of DEBUG.
    If the logger does not already have handlers, it adds a StreamHandler
    with a specific log message format and timestamp.
    Args:
        name (str): The name of the logger. Defaults to "hybrid_rag_analysis".
    Returns:
        logging.Logger: A configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
