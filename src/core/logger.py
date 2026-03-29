"""
Logger padronizado do projeto.
Prefixos: [INFO], [ERRO], [DEBUG], [WARN]
"""

import logging
import sys


def setup_logger(name: str = "agentespika", level: str = "INFO") -> logging.Logger:
    """Cria logger com formato padrao do projeto"""

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Evita duplicar handlers
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# Logger global
log = setup_logger()
