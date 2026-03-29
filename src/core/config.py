"""
Configuracoes centralizadas do projeto.
Carrega variaveis de ambiente e valida antes de iniciar.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Configuracoes carregadas do .env"""

    # Claude API
    anthropic_api_key: str = Field(..., description="Chave da API Anthropic")
    claude_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Modelo Claude a usar"
    )

    # Telegram Bot Tokens
    ceo_bot_token: str = Field(..., description="Token do bot CEO (Viktor)")
    dev_bot_token: str = Field(..., description="Token do bot Dev (Kai)")
    lider_bot_token: str = Field(..., description="Token do bot Lider (Alex)")
    designer_bot_token: str = Field(..., description="Token do bot Designer (Luna)")
    financeiro_bot_token: str = Field(..., description="Token do bot Financeiro (Max)")

    # Telegram Group
    telegram_group_id: int = Field(
        default=0,
        description="ID do grupo Telegram (preenchido automaticamente)"
    )

    # Limites
    max_history_messages: int = Field(
        default=20,
        description="Maximo de mensagens no historico de contexto"
    )
    max_tokens_response: int = Field(
        default=2048,
        description="Maximo de tokens por resposta do Claude"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Nivel de log")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    def get_bot_tokens(self) -> dict[str, str]:
        """Retorna mapa agente -> token"""
        return {
            "ceo": self.ceo_bot_token,
            "dev": self.dev_bot_token,
            "lider": self.lider_bot_token,
            "designer": self.designer_bot_token,
            "financeiro": self.financeiro_bot_token,
        }


# Singleton — importar de qualquer lugar
settings = Settings()
