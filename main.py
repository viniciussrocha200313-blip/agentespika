import os
import logging
from contextlib import asynccontextmanager
from http import HTTPStatus

from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, MessageHandler, filters

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carrega tokens
TOKENS = {
    "ceo": os.getenv("CEO_BOT_TOKEN", "").strip(),
    "dev": os.getenv("DEV_BOT_TOKEN", "").strip(),
    "lider": os.getenv("LIDER_BOT_TOKEN", "").strip(),
    "designer": os.getenv("DESIGNER_BOT_TOKEN", "").strip(),
    "financeiro": os.getenv("FINANCEIRO_BOT_TOKEN", "").strip(),
}

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip()
GROUP_ID = int(os.getenv("TELEGRAM_GROUP_ID", "0"))
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Valida tudo no startup
for name, token in TOKENS.items():
    if not token or ":" not in token:
        raise ValueError(f"Token {name} inválido: '{token}'")
    logger.info(f"[OK] Token {name}: {token.split(':')[0]}:***")

if not RENDER_URL:
    raise ValueError("RENDER_EXTERNAL_URL não configurado")

logger.info(f"[OK] RENDER_URL: {RENDER_URL}")
logger.info(f"[OK] GROUP_ID: {GROUP_ID}")

# Configura Gemini
genai.configure(api_key=GEMINI_KEY)
gemini = genai.GenerativeModel("gemini-2.0-flash")

# Histórico em memória
historico = []

# System prompts dos agentes
PROMPTS = {
    "ceo": """Você é Viktor, CEO do time de IA do Vinicius Souza.
Estrategista, direto, pensa grande. Fala em português.
Nunca começa com "Claro!" ou validação vazia. Máximo 3 parágrafos.
Termina sempre com uma pergunta ou provocação.""",

    "dev": """Você é Kai, dev sênior do time do Vinicius Souza.
Stack: Python, FastAPI, Node.js, Supabase, Claude API, Meta Graph API.
Direto ao ponto. Se a pergunta é técnica, inclui código real. Fala em português.""",

    "lider": """Você é Alex, líder de projetos do time do Vinicius Souza.
Transforma ideias em tarefas concretas. Termina sempre com "Próximo passo:".
Fala em português.""",

    "designer": """Você é Luna, designer do time do Vinicius Souza.
UI/UX, copy, campanhas. Criativa mas com fundamento. Fala em português.""",

    "financeiro": """Você é Max, financeiro do time do Vinicius Souza.
Números, ROI, viabilidade. Formato: Custo → Receita → ROI → Recomendação.
Fala em português.""",
}

# Cria um Application PTB para cada bot (sem updater = modo webhook)
apps: dict[str, Application] = {}
for nome, token in TOKENS.items():
    app_ptb = (
        Application.builder()
        .updater(None)  # CRÍTICO: desabilita polling
        .token(token)
        .build()
    )
    apps[nome] = app_ptb


async def orquestrador(texto: str) -> str:
    """Decide qual agente responde"""
    prompt = f"""Analise a mensagem e retorne APENAS o nome do agente.
Regras: código/técnico→dev | estratégia/negócio→ceo | tarefas/plano→lider
copy/design→designer | dinheiro/ROI→financeiro | dúvida geral→ceo

Mensagem: {texto}
Responda apenas com: ceo, dev, lider, designer ou financeiro"""
    try:
        r = gemini.generate_content(prompt)
        agente = r.text.strip().lower()
        if agente not in PROMPTS:
            return "ceo"
        return agente
    except Exception as e:
        logger.error(f"[ORQUESTRADOR] Erro: {e}")
        return "ceo"


async def responder(agente: str, mensagem: str) -> str:
    """Chama Gemini com o system prompt do agente"""
    ctx = "\n".join([f"{m['role']} ({m['name']}): {m['text']}"
                     for m in historico[-8:]])
    prompt = f"""{PROMPTS[agente]}

Histórico:
{ctx}

Mensagem atual: {mensagem}
Responda agora:"""
    try:
        r = gemini.generate_content(prompt)
        return r.text.strip()
    except Exception as e:
        logger.error(f"[{agente.upper()}] Erro: {e}")
        return f"Erro ao processar: {e}"


async def handle_message(update: Update, context):
    """Handler único que todos os bots usam"""
    if not update.message or not update.message.text:
        return
    if update.message.chat_id != GROUP_ID:
        return
    if update.message.from_user and update.message.from_user.is_bot:
        return

    texto = update.message.text
    username = update.message.from_user.username or update.message.from_user.first_name
    logger.info(f"[MSG] {username}: {texto}")

    historico.append({"role": "user", "name": username, "text": texto})
    if len(historico) > 50:
        historico.pop(0)

    agente = await orquestrador(texto)
    logger.info(f"[ORQUESTRADOR] → {agente}")

    resposta = await responder(agente, texto)
    historico.append({"role": "assistant", "name": agente, "text": resposta})

    try:
        await apps[agente].bot.send_message(
            chat_id=GROUP_ID,
            text=resposta,
            parse_mode="Markdown"
        )
        logger.info(f"[{agente.upper()}] Respondeu com sucesso")
    except Exception:
        await apps[agente].bot.send_message(
            chat_id=GROUP_ID,
            text=resposta
        )


# Adiciona handler em todos os apps
for app_ptb in apps.values():
    app_ptb.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Inicializa e registra webhook de cada bot
    for nome, app_ptb in apps.items():
        await app_ptb.initialize()
        await app_ptb.start()
        webhook_url = f"{RENDER_URL}/webhook/{nome}"
        await app_ptb.bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True,
            allowed_updates=["message"]
        )
        info = await app_ptb.bot.get_webhook_info()
        logger.info(f"[WEBHOOK] {nome}: {info.url} | pending: {info.pending_update_count}")
        logger.info(f"[SISTEMA] Bot {nome} online ✅")

    logger.info("[SISTEMA] Todos os bots online. Aguardando mensagens...")
    yield

    # Shutdown limpo
    for app_ptb in apps.values():
        await app_ptb.stop()
        await app_ptb.shutdown()


fastapi_app = FastAPI(lifespan=lifespan)


@fastapi_app.get("/")
async def health():
    return {"status": "ok", "bots": list(apps.keys())}


@fastapi_app.get("/webhook/info")
async def webhook_info():
    infos = {}
    for nome, app_ptb in apps.items():
        info = await app_ptb.bot.get_webhook_info()
        infos[nome] = {
            "url": info.url,
            "pending": info.pending_update_count,
            "last_error": info.last_error_message
        }
    return infos


# Endpoint webhook para cada bot
@fastapi_app.post("/webhook/{bot_name}")
async def webhook(bot_name: str, request: Request):
    if bot_name not in apps:
        return Response(status_code=404)
    data = await request.json()
    update = Update.de_json(data, apps[bot_name].bot)
    await apps[bot_name].process_update(update)
    return Response(status_code=HTTPStatus.OK)
