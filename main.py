import os
import asyncio
import logging
from contextlib import asynccontextmanager
from http import HTTPStatus

from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, MessageHandler, filters

import google.generativeai as genai
from groq import Groq
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
GROQ_KEY = os.getenv("GROQ_API_KEY", "").strip()

# Valida tokens no startup
for name, token in TOKENS.items():
    if not token or ":" not in token:
        raise ValueError(f"Token {name} invalido: '{token}'")
    logger.info(f"[OK] Token {name}: {token.split(':')[0]}:***")

if not RENDER_URL:
    raise ValueError("RENDER_EXTERNAL_URL nao configurado")

logger.info(f"[OK] RENDER_URL: {RENDER_URL}")
logger.info(f"[OK] GROUP_ID: {GROUP_ID}")
logger.info(f"[OK] Groq: {'configurado' if GROQ_KEY else 'ausente'}")
logger.info(f"[OK] Gemini: {'configurado' if GEMINI_KEY else 'ausente'}")

# Configura Gemini (respostas dos agentes)
genai.configure(api_key=GEMINI_KEY)
gemini = genai.GenerativeModel("gemini-2.0-flash")

# Configura Groq (orquestrador - rapido e sem cota restritiva)
groq_client = Groq(api_key=GROQ_KEY)

# Historico em memoria
historico = []

# System prompts dos agentes
PROMPTS = {
    "ceo": """Voce e Viktor, CEO do time de IA do Vinicius Souza.
Estrategista, direto, pensa grande. Fala em portugues.
Nunca comeca com "Claro!" ou validacao vazia. Maximo 3 paragrafos.
Termina sempre com uma pergunta ou provocacao.""",

    "dev": """Voce e Kai, dev senior do time do Vinicius Souza.
Stack: Python, FastAPI, Node.js, Supabase, Claude API, Meta Graph API.
Direto ao ponto. Se a pergunta e tecnica, inclui codigo real. Fala em portugues.""",

    "lider": """Voce e Alex, lider de projetos do time do Vinicius Souza.
Transforma ideias em tarefas concretas. Termina sempre com "Proximo passo:".
Fala em portugues.""",

    "designer": """Voce e Luna, designer do time do Vinicius Souza.
UI/UX, copy, campanhas. Criativa mas com fundamento. Fala em portugues.""",

    "financeiro": """Voce e Max, financeiro do time do Vinicius Souza.
Numeros, ROI, viabilidade. Formato: Custo -> Receita -> ROI -> Recomendacao.
Fala em portugues.""",
}

# Cria um Application PTB para cada bot (sem updater = modo webhook)
apps: dict[str, Application] = {}
for nome, token in TOKENS.items():
    app_ptb = (
        Application.builder()
        .updater(None)  # CRITICO: desabilita polling
        .token(token)
        .build()
    )
    apps[nome] = app_ptb

async def orquestrador(texto: str) -> str:
    """Usa Groq (llama-3.3-70b) para decidir qual agente responde - rapido e sem cota restritiva"""
    prompt = f"""Analise a mensagem e retorne APENAS o nome do agente.
Regras: codigo/tecnico->dev | estrategia/negocio->ceo | tarefas/plano->lider
copy/design->designer | dinheiro/ROI->financeiro | duvida geral->ceo

Mensagem: {texto}
Responda apenas com: ceo, dev, lider, designer ou financeiro"""
    try:
        r = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0
        )
        agente = r.choices[0].message.content.strip().lower()
        if agente not in PROMPTS:
            return "ceo"
        return agente
    except Exception as e:
        logger.error(f"[ORQUESTRADOR] Erro Groq: {e}")
        return "ceo"

async def responder(agente: str, mensagem: str) -> str:
    """Usa Gemini para gerar a resposta. Fallback automatico para Groq se Gemini falhar."""
    ctx = "\n".join([f"{m['role']} ({m['name']}): {m['text']}"
                     for m in historico[-8:]])
    prompt = f"""{PROMPTS[agente]}

Historico:
{ctx}

Mensagem atual: {mensagem}
Responda agora:"""
    # Tenta Gemini
    try:
        r = gemini.generate_content(prompt)
        logger.info(f"[{agente}] Respondeu via Gemini")
        return r.text.strip()
    except Exception as e:
        logger.warning(f"[{agente}] Gemini falhou ({e}), ativando fallback Groq...")
    # Fallback: Groq
    try:
        r = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": PROMPTS[agente]},
                {"role": "user", "content": mensagem}
            ],
            max_tokens=512,
            temperature=0.7
        )
        logger.info(f"[{agente}] Respondeu via Groq (fallback)")
        return r.choices[0].message.content.strip()
    except Exception as e2:
        logger.error(f"[{agente}] Groq tambem falhou: {e2}")
        return "Sistema temporariamente sobrecarregado. Tenta em instantes!"

async def handle_message(update: Update, context):
    """Handler unico que todos os bots usam"""
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
    logger.info(f"[ORQUESTRADOR] -> {agente}")

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

# Apenas o bot CEO recebe mensagens — ele e o roteador
# Os demais bots so existem para enviar com sua propria identidade
apps["ceo"].add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    handle_message
))

@asynccontextmanager
async def lifespan(_: FastAPI):
    for nome, app_ptb in apps.items():
        await app_ptb.initialize()
        await app_ptb.start()

    # So o CEO tem webhook ativo para receber mensagens
    webhook_url = f"{RENDER_URL}/webhook/ceo"
    await apps["ceo"].bot.set_webhook(
        url=webhook_url,
        drop_pending_updates=True,
        allowed_updates=["message"]
    )
    info = await apps["ceo"].bot.get_webhook_info()
    logger.info(f"[WEBHOOK] ceo (roteador): {info.url} | pending: {info.pending_update_count}")

    # Os outros bots removem qualquer webhook antigo
    for nome in ["dev", "lider", "designer", "financeiro"]:
        await apps[nome].bot.delete_webhook(drop_pending_updates=True)
        logger.info(f"[SISTEMA] Bot {nome} online (apenas envio)")

    logger.info("[SISTEMA] Todos os bots online. CEO recebe, agentes respondem.")

    logger.info("[SISTEMA] Todos os bots online. Aguardando mensagens...")
    yield

    # Shutdown limpo
    for app_ptb in apps.values():
        await app_ptb.stop()
        await app_ptb.shutdown()

fastapi_app = FastAPI(lifespan=lifespan)

@fastapi_app.get("/")
async def health():
    return {"status": "ok", "bots": list(apps.keys()), "orquestrador": "groq", "agentes": "gemini"}

@fastapi_app.get("/webhook/info")
async def webhook_info():
    info = await apps["ceo"].bot.get_webhook_info()
    return {
        "ceo": {
            "url": info.url,
            "pending": info.pending_update_count,
            "last_error": info.last_error_message
        },
        "outros": "dev/lider/designer/financeiro so enviam, sem webhook"
    }

# So o CEO recebe atualizacoes do Telegram
@fastapi_app.post("/webhook/ceo")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, apps["ceo"].bot)
    await apps["ceo"].process_update(update)
    return Response(status_code=HTTPStatus.OK)
