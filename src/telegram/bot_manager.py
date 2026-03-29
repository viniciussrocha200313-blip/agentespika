"""
Gerenciador dos bots Telegram.
Cada agente tem seu proprio bot. Todos escutam o mesmo grupo.
Apenas UM bot (o CEO, por padrao) recebe as mensagens do user.
Os outros enviam respostas quando o orquestrador manda.
"""

import asyncio

from telegram import Update, Bot
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)

from src.agents.orchestrator import Orchestrator
from src.agents.prompts import AGENT_NAMES
from src.core.config import settings
from src.core.logger import log


class BotManager:
    """
    Gerencia todos os 5 bots do time.
    - Um bot "listener" (CEO) recebe todas as mensagens do grupo
    - Cada bot envia suas proprias respostas
    - O orquestrador decide quem responde
    """

    def __init__(self):
        self._orchestrator = Orchestrator()
        self._bots: dict[str, Bot] = {}
        self._apps: list[Application] = []
        self._group_id: int = settings.telegram_group_id
        self._processing = False  # Trava para evitar respostas simultaneas

    async def initialize(self) -> None:
        """Inicializa todos os bots"""
        tokens = settings.get_bot_tokens()

        for agent_id, token in tokens.items():
            bot = Bot(token=token)
            bot_info = await bot.get_me()
            self._bots[agent_id] = bot
            log.info(
                "Bot %s (@%s) inicializado — ID: %s",
                AGENT_NAMES[agent_id],
                bot_info.username,
                bot_info.id,
            )

        log.info("Todos os %d bots inicializados", len(self._bots))

    def _build_listener_app(self) -> Application:
        """
        Constroi a Application do bot listener (CEO).
        Ele eh quem recebe as mensagens do grupo e dispara o pipeline.
        """
        app = (
            Application.builder()
            .token(settings.ceo_bot_token)
            .build()
        )

        # Handler para mensagens de texto no grupo
        app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
                self._handle_group_message,
            )
        )

        # Comando /start — identifica o grupo
        app.add_handler(
            CommandHandler("start", self._handle_start)
        )

        # Comando /ping — health check
        app.add_handler(
            CommandHandler("ping", self._handle_ping)
        )

        # Comando /reset — limpa historico
        app.add_handler(
            CommandHandler("reset", self._handle_reset)
        )

        return app

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Registra o group_id e confirma"""
        chat = update.effective_chat
        if chat and chat.type in ("group", "supergroup"):
            self._group_id = chat.id
            log.info("Group ID registrado: %s", self._group_id)
            await update.message.reply_text(
                "🟢 Fazza AI Team ativo.\n"
                f"Group ID: `{self._group_id}`\n\n"
                "Envie qualquer mensagem e o time responde.",
                parse_mode="Markdown",
            )

    async def _handle_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Health check simples"""
        bots_online = len(self._bots)
        memory_size = self._orchestrator._memory.size
        await update.message.reply_text(
            f"🏓 Pong!\n"
            f"Bots online: {bots_online}/5\n"
            f"Mensagens no contexto: {memory_size}",
        )

    async def _handle_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Limpa o historico de contexto"""
        self._orchestrator._memory.clear()
        await update.message.reply_text("🔄 Contexto limpo. Começando do zero.")
        log.info("Historico limpo por comando /reset")

    async def _handle_group_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handler principal — recebe mensagem do grupo, roteia pelo orquestrador,
        e envia respostas pelos bots corretos.
        """
        message = update.message
        if not message or not message.text:
            return

        # Ignora mensagens de bots (evita loop)
        if message.from_user and message.from_user.is_bot:
            return

        # Trava — processa uma mensagem por vez
        if self._processing:
            log.debug("Mensagem ignorada — processando outra")
            return

        self._processing = True
        user_text = message.text
        chat_id = message.chat_id
        user_name = message.from_user.first_name if message.from_user else "User"

        log.info("Mensagem de %s: %s", user_name, user_text[:80])

        # Registra group_id se ainda nao tem
        if self._group_id == 0:
            self._group_id = chat_id
            log.info("Group ID auto-registrado: %s", self._group_id)

        try:
            # Pipeline do orquestrador
            responses = await self._orchestrator.process_message(user_text)

            # Envia cada resposta pelo bot correto
            for agent_id, response_text in responses.items():
                bot = self._bots.get(agent_id)
                if not bot:
                    log.error("Bot %s nao encontrado", agent_id)
                    continue

                # Divide mensagens longas (limite Telegram: 4096 chars)
                chunks = self._split_message(response_text)
                for chunk in chunks:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode="Markdown",
                    )
                    # Pequeno delay entre chunks
                    if len(chunks) > 1:
                        await asyncio.sleep(0.5)

                # Delay entre agentes diferentes
                if len(responses) > 1:
                    await asyncio.sleep(1)

        except Exception as e:
            log.error("Erro ao processar mensagem: %s", e)
            # Responde com o bot CEO em caso de erro
            ceo_bot = self._bots.get("ceo")
            if ceo_bot:
                await ceo_bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ Erro interno. Tenta de novo em alguns segundos.",
                )
        finally:
            self._processing = False

    @staticmethod
    def _split_message(text: str, max_length: int = 4000) -> list[str]:
        """
        Divide mensagem longa respeitando o limite do Telegram.
        Tenta quebrar em paragrafos para nao cortar no meio da frase.
        """
        if len(text) <= max_length:
            return [text]

        chunks = []
        while text:
            if len(text) <= max_length:
                chunks.append(text)
                break

            # Tenta quebrar no ultimo paragrafo dentro do limite
            split_pos = text.rfind("\n\n", 0, max_length)
            if split_pos == -1:
                # Se nao tem paragrafo, quebra no ultimo espaco
                split_pos = text.rfind(" ", 0, max_length)
            if split_pos == -1:
                # Ultimo recurso — corta no limite
                split_pos = max_length

            chunks.append(text[:split_pos])
            text = text[split_pos:].lstrip()

        return chunks

    async def run(self) -> None:
        """Inicia o bot listener com polling"""
        app = self._build_listener_app()
        self._apps.append(app)

        log.info("Iniciando polling do bot listener (CEO)...")

        # Inicializa a app
        await app.initialize()
        await app.start()
        await app.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=["message"],
        )

        log.info("🟢 Fazza AI Team rodando — aguardando mensagens no grupo")

        # Mantém rodando
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            log.info("Desligando bots...")
        finally:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
            log.info("Bots desligados com sucesso")
