import asyncio
import os
import logging
import sys
from dotenv import load_dotenv

load_dotenv()

# ===== VALIDACAO DE TOKENS =====
print("=" * 50)
print("VALIDANDO VARIAVEIS DE AMBIENTE")
print("=" * 50)

_token_names = {
    "CEO": "CEO_BOT_TOKEN",
    "DEV": "DEV_BOT_TOKEN",
    "LIDER": "LIDER_BOT_TOKEN",
    "DESIGNER": "DESIGNER_BOT_TOKEN",
    "FINANCEIRO": "FINANCEIRO_BOT_TOKEN",
}

_all_ok = True
for label, env_name in _token_names.items():
    token = os.getenv(env_name, "").strip()
    if not token:
        print(f"[ERRO] Token {label} ({env_name}) NAO encontrado!")
        _all_ok = False
    elif ":" not in token:
        print(f"[ERRO] Token {label} parece invalido: {token[:20]}...")
        _all_ok = False
    else:
        bot_id = token.split(":")[0]
        print(f"[OK] Token {label} carregado: {bot_id}:***")

_gemini = os.getenv("GEMINI_API_KEY", "").strip()
if _gemini:
    print(f"[OK] GEMINI_API_KEY carregada: {_gemini[:10]}...")
else:
    print("[ERRO] GEMINI_API_KEY nao encontrada!")
    _all_ok = False

_gid = os.getenv("TELEGRAM_GROUP_ID", "").strip()
print(f"[OK] GROUP_ID: {_gid}" if _gid else "[ERRO] GROUP_ID nao configurado!")

if not _all_ok:
    print("[FATAL] Variaveis de ambiente com erro. Abortando.")
    sys.exit(1)

print("=" * 50)
# ===== FIM VALIDACAO =====

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from orchestrator import Orchestrator
from agents.ceo import CeoAgent
from agents.dev import DevAgent
from agents.lider import LiderAgent
from agents.designer import DesignerAgent
from agents.financeiro import FinanceiroAgent
from memory.history import History

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

history = History()
orchestrator = Orchestrator()

agents = {
    "ceo": CeoAgent(),
    "dev": DevAgent(),
    "lider": LiderAgent(),
    "designer": DesignerAgent(),
    "financeiro": FinanceiroAgent(),
}

TOKENS = {
    "ceo": os.getenv("CEO_BOT_TOKEN"),
    "dev": os.getenv("DEV_BOT_TOKEN"),
    "lider": os.getenv("LIDER_BOT_TOKEN"),
    "designer": os.getenv("DESIGNER_BOT_TOKEN"),
    "financeiro": os.getenv("FINANCEIRO_BOT_TOKEN"),
}

GROUP_ID = int(os.getenv("TELEGRAM_GROUP_ID", "0"))

bot_apps = {
    name: Application.builder().token(token).build()
    for name, token in TOKENS.items()
    if token
}


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if GROUP_ID != 0 and update.message.chat_id != GROUP_ID:
        return
    if update.message.from_user and update.message.from_user.is_bot:
        return

    text = update.message.text
    sender = update.message.from_user
    username = sender.username or sender.first_name if sender else "User"
    logger.info(f"[MSG] {username}: {text}")

    history.add("user", username, text)

    chosen = await orchestrator.route(text, history.get())
    agent_names = [a.strip() for a in chosen.split(",")]
    logger.info(f"[ORQUESTRADOR] escolheu: {agent_names}")

    for agent_name in agent_names:
        if agent_name not in agents:
            continue
        agent = agents[agent_name]
        response = await agent.respond(text, history.get())
        if response:
            history.add("assistant", agent_name, response)
            try:
                await bot_apps[agent_name].bot.send_message(
                    chat_id=update.message.chat_id,
                    text=response,
                    parse_mode="Markdown"
                )
                logger.info(f"[{agent_name.upper()}] respondeu com sucesso")
            except Exception as e:
                logger.warning(f"[{agent_name.upper()}] Markdown falhou, enviando sem: {e}")
                try:
                    await bot_apps[agent_name].bot.send_message(
                        chat_id=update.message.chat_id,
                        text=response
                    )
                    logger.info(f"[{agent_name.upper()}] respondeu (sem markdown)")
                except Exception as e2:
                    logger.error(f"[{agent_name.upper()}] falhou ao enviar: {e2}")
            await asyncio.sleep(2)


async def main():
    logger.info("=" * 50)
    logger.info("FAZZA AI TEAM - Iniciando")
    logger.info("=" * 50)
    logger.info(f"[SISTEMA] GROUP_ID configurado: {GROUP_ID}")
    logger.info(f"[SISTEMA] Bots a inicializar: {list(bot_apps.keys())}")

    # Adiciona handler em todos os apps
    for app in bot_apps.values():
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))

    # Inicializa e inicia cada app manualmente (nao usa run_polling)
    for name, app in bot_apps.items():
        await app.initialize()
        await app.start()
        await app.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=["message"]
        )
        bot_info = await app.bot.get_me()
        logger.info(f"[SISTEMA] Bot {name} online (@{bot_info.username})")

    logger.info("[SISTEMA] Todos os bots rodando. Aguardando mensagens...")

    # Mantem o processo vivo
    stop_event = asyncio.Event()
    await stop_event.wait()


if __name__ == "__main__":
    asyncio.run(main())
