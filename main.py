import asyncio
import os
import logging
import sys
import json
import threading
import time
from dotenv import load_dotenv

load_dotenv()

# ===== VALIDACAO DE TOKENS =====
print("=" * 50)
print("VALIDANDO VARIAVEIS DE AMBIENTE")
print("=" * 50)

_token_map = {
    "CEO": "CEO_BOT_TOKEN",
    "DEV": "DEV_BOT_TOKEN",
    "LIDER": "LIDER_BOT_TOKEN",
    "DESIGNER": "DESIGNER_BOT_TOKEN",
    "FINANCEIRO": "FINANCEIRO_BOT_TOKEN",
}

_all_ok = True
for label, env_name in _token_map.items():
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

_render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
print(f"[OK] RENDER_URL: {_render_url}" if _render_url else "[INFO] RENDER_EXTERNAL_URL nao definida (modo local)")

if not _all_ok:
    print("[FATAL] Variaveis de ambiente com erro. Abortando.")
    sys.exit(1)

print("=" * 50)
# ===== FIM VALIDACAO =====

from aiohttp import web
import aiohttp
from telegram import Bot, Update
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
    "ceo": os.getenv("CEO_BOT_TOKEN", "").strip(),
    "dev": os.getenv("DEV_BOT_TOKEN", "").strip(),
    "lider": os.getenv("LIDER_BOT_TOKEN", "").strip(),
    "designer": os.getenv("DESIGNER_BOT_TOKEN", "").strip(),
    "financeiro": os.getenv("FINANCEIRO_BOT_TOKEN", "").strip(),
}

GROUP_ID = int(os.getenv("TELEGRAM_GROUP_ID", "0").strip())
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip()
PORT = int(os.getenv("PORT", "10000").strip())

# Bots do Telegram (um por agente)
bots = {name: Bot(token=token) for name, token in TOKENS.items() if token}

# Mapa token -> nome do agente (pra saber qual bot recebeu o update)
TOKEN_TO_AGENT = {token: name for name, token in TOKENS.items() if token}


async def process_message(text: str, chat_id: int, username: str):
    """Processa uma mensagem: roteia pelo orquestrador e responde com o agente correto"""
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
            bot = bots.get(agent_name)
            if bot:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=response,
                        parse_mode="Markdown"
                    )
                    logger.info(f"[{agent_name.upper()}] respondeu com sucesso")
                except Exception as e:
                    logger.warning(f"[{agent_name.upper()}] Markdown falhou: {e}")
                    try:
                        await bot.send_message(chat_id=chat_id, text=response)
                        logger.info(f"[{agent_name.upper()}] respondeu (sem markdown)")
                    except Exception as e2:
                        logger.error(f"[{agent_name.upper()}] falhou ao enviar: {e2}")
            await asyncio.sleep(2)


async def webhook_handler(request):
    """Recebe updates do Telegram via webhook POST"""
    try:
        # Extrai o token da URL pra saber qual bot recebeu
        token = request.match_info.get("token", "")
        data = await request.json()

        update = Update.de_json(data, bots.get("ceo"))

        if not update or not update.message or not update.message.text:
            return web.Response(text="ok")

        msg = update.message

        # Filtra: so grupo configurado
        if GROUP_ID != 0 and msg.chat_id != GROUP_ID:
            return web.Response(text="ok")

        # Ignora bots
        if msg.from_user and msg.from_user.is_bot:
            return web.Response(text="ok")

        username = msg.from_user.username or msg.from_user.first_name if msg.from_user else "User"

        # Processa em background pra responder rapido ao Telegram
        asyncio.create_task(process_message(msg.text, msg.chat_id, username))

        return web.Response(text="ok")
    except Exception as e:
        logger.error(f"[WEBHOOK] Erro: {e}")
        return web.Response(text="error", status=500)


async def health_handler(request):
    """Health check pro Render"""
    return web.json_response({
        "status": "ok",
        "bots": list(bots.keys()),
        "group_id": GROUP_ID,
        "messages_in_context": len(history.get()),
    })


def keep_alive():
    """Ping a cada 10 minutos pra Render nao dormir"""
    if not RENDER_URL:
        logger.info("[KEEP-ALIVE] RENDER_EXTERNAL_URL nao definida, desativado")
        return
    logger.info(f"[KEEP-ALIVE] Ativo para: {RENDER_URL}")
    while True:
        try:
            import requests
            requests.get(f"{RENDER_URL}/health", timeout=10)
            logger.info("[KEEP-ALIVE] Ping enviado")
        except Exception as e:
            logger.warning(f"[KEEP-ALIVE] Erro: {e}")
        time.sleep(600)


async def setup_webhooks():
    """Configura webhook de cada bot pra apontar pro Render"""
    if not RENDER_URL:
        logger.warning("[WEBHOOK] RENDER_EXTERNAL_URL nao definida - webhooks nao configurados")
        return False

    for name, bot in bots.items():
        token = TOKENS[name]
        webhook_url = f"{RENDER_URL}/webhook/{token}"
        try:
            await bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True,
                allowed_updates=["message"]
            )
            bot_info = await bot.get_me()
            logger.info(f"[WEBHOOK] Bot {name} (@{bot_info.username}) -> {RENDER_URL}/webhook/***")
        except Exception as e:
            logger.error(f"[WEBHOOK] Erro ao configurar {name}: {e}")
            return False

    return True


async def main():
    logger.info("=" * 50)
    logger.info("FAZZA AI TEAM - Iniciando")
    logger.info("=" * 50)
    logger.info(f"[SISTEMA] GROUP_ID: {GROUP_ID}")
    logger.info(f"[SISTEMA] Porta: {PORT}")
    logger.info(f"[SISTEMA] Render URL: {RENDER_URL or 'local'}")

    # Keep-alive em thread separada
    threading.Thread(target=keep_alive, daemon=True).start()

    # Configura webhooks
    if RENDER_URL:
        success = await setup_webhooks()
        if success:
            logger.info("[SISTEMA] Webhooks configurados com sucesso")
        else:
            logger.error("[SISTEMA] Falha ao configurar webhooks")

    # Servidor HTTP
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_post("/webhook/{token}", webhook_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logger.info(f"[SISTEMA] Servidor HTTP rodando na porta {PORT}")
    logger.info("[SISTEMA] Todos os bots configurados. Aguardando mensagens via webhook...")

    # Mantem rodando
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
