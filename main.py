"""
Fazza AI Team — Backend principal.
Inicia todos os bots e o orquestrador.

Uso:
    python main.py
"""

import asyncio
import sys
from pathlib import Path

# Adiciona o diretorio raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from src.core.config import settings
from src.core.logger import log, setup_logger
from src.telegram.bot_manager import BotManager


async def main():
    """Inicializa e roda o time de agentes"""

    # Configura nivel de log
    setup_logger(level=settings.log_level)

    log.info("=" * 50)
    log.info("FAZZA AI TEAM — Iniciando")
    log.info("=" * 50)
    log.info("Modelo: %s", settings.claude_model)
    log.info("Historico max: %d mensagens", settings.max_history_messages)

    # Cria e inicializa o gerenciador de bots
    manager = BotManager()
    await manager.initialize()

    # Roda
    await manager.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Desligado pelo usuario")
    except Exception as e:
        log.error("Erro fatal: %s", e)
        sys.exit(1)
