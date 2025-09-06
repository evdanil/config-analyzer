import logging
import os
from typing import Optional


_LOGGER: Optional[logging.Logger] = None


def get_logger(name: str = "config_analyzer") -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER.getChild(name)

    logger = logging.getLogger("config_analyzer")
    if logger.handlers:
        _LOGGER = logger
        return logger.getChild(name)

    level_env = os.environ.get("CONFIG_ANALYZER_DEBUG", "0").lower()
    level = logging.DEBUG if level_env in {"1", "true", "yes", "on", "debug"} else logging.INFO
    logger.setLevel(level)

    log_path = os.environ.get("CONFIG_ANALYZER_LOG", os.path.join(os.getcwd(), "tui_debug.log"))
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    _LOGGER = logger
    return logger.getChild(name)

