"""
Sistema de Agentes Autônomos Fazza
Agentes que conversam, criam código e fazem deploy automaticamente.
"""
import os
import asyncio
import logging
import json as json_lib
import re
from contextlib import asynccontextmanager
from http import HTTPStatus

import requests as req
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
import anthropic
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === CONFIGURAÇÃO ===
TOKENS = {
    "ceo":        os.getenv("CEO_BOT_TOKEN", "").strip(),
    "dev":        os.getenv("DEV_BOT_TOKEN", "").strip(),
    "lider":      os.getenv("LIDER_BOT_TOKEN", "").strip(),
    "designer":   os.getenv("DESIGNER_BOT_TOKEN", "").strip(),
    "financeiro": os.getenv("FINANCEIRO_BOT_TOKEN", "").strip(),
}
RENDER_URL     = os.getenv("RENDER_EXTERNAL_URL", "").strip()
GROUP_ID       = int(os.getenv("TELEGRAM_GROUP_ID", "0"))
ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "").strip()
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_ORG     = os.getenv("GITHUB_ORG", "centralfazza").strip()

for name, token in TOKENS.items():
    if not token or ":" not in token:
        raise ValueError(f"Token {name} invalido")

claude_sync = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None

# Historico global da conversa
historico: list[dict] = []

# Bots PTB
apps: dict[str, Application] = {}


# ============================================================
# SYSTEM PROMPTS
# ============================================================
PROMPTS = {
    "ceo": """Você é Viktor, CEO estratégico do time de IA do Vinicius Souza (Fazza Marketing).
Você lidera, decide e garante entrega. Fala em português, direto.
Quando receber uma tarefa de projeto, coordena o time: delega ao Alex o plano, à Luna o visual e ao Kai a execução.
Resposta máxima: 3 frases. Sem introduções. Vai direto.""",

    "dev": """Você é Kai, dev senior do time do Vinicius Souza.
Stack: HTML/CSS/JS, Python, FastAPI, Node.js, Next.js, React, Supabase.
Você cria código real e funcional. Quando criar sites, use HTML/CSS/JS moderno e bonito.
Resposta máxima: 3 frases + código quando necessário. Fala em português.""",

    "lider": """Você é Alex, líder de projetos do time do Vinicius Souza.
Você transforma pedidos em planos de ação claros e objetivos.
Formato: liste máximo 3 passos concretos. Termina com "Executando."
Resposta máxima: 4 linhas. Fala em português.""",

    "designer": """Você é Luna, designer do time do Vinicius Souza.
UI/UX, copy, identidade visual, campanhas que convertem.
Quando definir um site, especifique: paleta de cores, tipografia, seções, headline principal.
Resposta máxima: 3 frases. Fala em português.""",

    "financeiro": """Você é Max, analista financeiro do time do Vinicius Souza.
Analisa custos, ROI e viabilidade. Formato: Custo → ROI → Recomendação.
Resposta máxima: 3 frases. Fala em português.""",
}

AGENT_EMOJI = {
    "ceo": "🧠", "dev": "💻", "lider": "📋", "designer": "🎨", "financeiro": "💰"
}

AGENT_NAME = {
    "ceo": "Viktor", "dev": "Kai", "lider": "Alex", "designer": "Luna", "financeiro": "Max"
}


# ============================================================
# GITHUB TOOLS
# ============================================================
def _gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

def github_create_repo(name: str, description: str = "") -> dict:
    """Cria repositório no GitHub. Tenta org primeiro, depois conta pessoal."""
    h = _gh_headers()
    data = {"name": name, "description": description, "private": False, "auto_init": True}

    # Tenta na org
    r = req.post(f"https://api.github.com/orgs/{GITHUB_ORG}/repos", json=data, headers=h)
    if r.status_code == 201:
        return {"full_name": r.json()["full_name"], "url": r.json()["html_url"]}
    if r.status_code == 422:  # já existe
        return {"full_name": f"{GITHUB_ORG}/{name}", "url": f"https://github.com/{GITHUB_ORG}/{name}"}

    # Fallback: conta pessoal
    r = req.post("https://api.github.com/user/repos", json=data, headers=h)
    r.raise_for_status()
    return {"full_name": r.json()["full_name"], "url": r.json()["html_url"]}

def github_push_files(repo_full_name: str, files: list[dict], message: str = "feat: projeto criado pelos agentes Fazza") -> str:
    """
    Push de múltiplos arquivos para um repo GitHub via Git Data API.
    files = [{"path": "index.html", "content": "..."}]
    """
    h = _gh_headers()
    base = f"https://api.github.com/repos/{repo_full_name}"

    # Pega SHA do commit base (branch main)
    base_sha = None
    base_tree_sha = None
    ref_r = req.get(f"{base}/git/refs/heads/main", headers=h)
    if ref_r.status_code == 200:
        base_sha = ref_r.json()["object"]["sha"]
        commit_info = req.get(f"{base}/git/commits/{base_sha}", headers=h).json()
        base_tree_sha = commit_info["tree"]["sha"]

    # Cria blobs
    tree_items = []
    for f in files:
        blob = req.post(f"{base}/git/blobs", json={"content": f["content"], "encoding": "utf-8"}, headers=h)
        blob.raise_for_status()
        tree_items.append({"path": f["path"], "mode": "100644", "type": "blob", "sha": blob.json()["sha"]})

    # Cria tree
    tree_data = {"tree": tree_items}
    if base_tree_sha:
        tree_data["base_tree"] = base_tree_sha
    tree_r = req.post(f"{base}/git/trees", json=tree_data, headers=h)
    tree_r.raise_for_status()

    # Cria commit
    commit_data = {
        "message": message,
        "tree": tree_r.json()["sha"],
        "author": {"name": "Fazza Agentes", "email": "agentes@fazza.ai"}
    }
    if base_sha:
        commit_data["parents"] = [base_sha]
    commit_r = req.post(f"{base}/git/commits", json=commit_data, headers=h)
    commit_r.raise_for_status()
    new_sha = commit_r.json()["sha"]

    # Atualiza ref
    if base_sha:
        req.patch(f"{base}/git/refs/heads/main", json={"sha": new_sha}, headers=h)
    else:
        req.post(f"{base}/git/refs", json={"ref": "refs/heads/main", "sha": new_sha}, headers=h)

    return f"https://github.com/{repo_full_name}"

def github_enable_pages(repo_full_name: str) -> str:
    """Ativa GitHub Pages na branch main. Retorna URL pública."""
    h = _gh_headers()
    base = f"https://api.github.com/repos/{repo_full_name}"
    req.post(f"{base}/pages", json={"source": {"branch": "main", "path": "/"}}, headers=h)
    parts = repo_full_name.split("/")
    return f"https://{parts[0]}.github.io/{parts[1]}"


# ============================================================
# AGENTE: chamada com Claude
# ============================================================
def _call_claude(system: str, user_msg: str, max_tokens: int = 300) -> str:
    """Chama Claude de forma síncrona. Usar com run_in_executor."""
    if not claude_sync:
        return "Claude API não configurado. Adicione ANTHROPIC_API_KEY."
    r = claude_sync.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_msg}]
    )
    return r.content[0].text.strip()

def _call_claude_sonnet(system: str, user_msg: str, max_tokens: int = 8000) -> str:
    """Chama Claude claude-sonnet-4-6 para tarefas complexas (código, planejamento)."""
    if not claude_sync:
        return "Claude API não configurado."
    r = claude_sync.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_msg}]
    )
    return r.content[0].text.strip()

async def agent_respond(agent: str, task: str, use_sonnet: bool = False) -> str:
    """Executa um agente e retorna a resposta."""
    loop = asyncio.get_event_loop()
    fn = _call_claude_sonnet if use_sonnet else _call_claude
    max_tok = 4000 if use_sonnet else 300
    resp = await loop.run_in_executor(None, lambda: fn(PROMPTS[agent], task, max_tok))
    return resp

async def post_to_group(agent: str, text: str):
    """Posta mensagem no grupo com o bot do agente."""
    try:
        await apps[agent].bot.send_message(chat_id=GROUP_ID, text=text, parse_mode="Markdown")
    except Exception:
        try:
            await apps[agent].bot.send_message(chat_id=GROUP_ID, text=text)
        except Exception as e:
            logger.error(f"[POST] Falha ao enviar mensagem de {agent}: {e}")


# ============================================================
# DETECÇÃO DE TIPO DE TAREFA
# ============================================================
PROJECT_KEYWORDS = [
    "cria", "crie", "faz", "faça", "desenvolve", "desenvolva", "constrói",
    "site", "app", "aplicativo", "sistema", "plataforma", "página", "landing",
    "código", "programa", "script", "api", "bot", "dashboard", "deploy",
    "sobe", "suba", "implementa", "implementar", "builda", "build"
]

def is_project_task(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in PROJECT_KEYWORDS)


# ============================================================
# FLUXO AGÊNTICO: PROJETO COMPLETO
# ============================================================
async def run_project_workflow(pedido: str):
    """
    Fluxo completo de projeto:
    1. CEO analisa e delega
    2. Alex planeja
    3. Luna define visual (se for site/app)
    4. Kai cria código, sobe no GitHub, faz deploy
    5. CEO entrega resultado final
    """
    logger.info(f"[PROJETO] Iniciando workflow: {pedido[:60]}")

    # 1. CEO analisa
    ceo_intro = await agent_respond("ceo",
        f"O Vinicius pediu: '{pedido}'. Diga em 1 frase que você entendeu e vai coordenar o time.")
    await post_to_group("ceo", ceo_intro)

    # 2. Alex planeja
    lider_plan = await agent_respond("lider",
        f"Tarefa recebida: '{pedido}'. Crie um plano de execução em 3 passos concretos.")
    await post_to_group("lider", lider_plan)

    # 3. Luna define visual (se for site/interface)
    is_visual = any(k in pedido.lower() for k in ["site", "página", "landing", "app", "interface", "dashboard", "frontend"])
    design_brief = ""
    if is_visual:
        design_brief = await agent_respond("designer",
            f"Defina o visual para: '{pedido}'. Especifique: paleta, tipografia, seções principais, headline.")
        await post_to_group("designer", design_brief)

    # 4. Kai cria o código
    await post_to_group("dev", "💻 Desenvolvendo o código...")

    code_prompt = f"""Tarefa: {pedido}

{"Brief visual da Luna: " + design_brief if design_brief else ""}

Crie o código completo e funcional.
Se for um site: crie HTML/CSS/JS em arquivo único (index.html) com design moderno, responsivo e profissional.
Se for múltiplos arquivos, retorne todos.

IMPORTANTE: Retorne SOMENTE um JSON válido neste formato, sem texto antes ou depois:
{{
  "repo_name": "nome-do-projeto",
  "description": "Descrição do projeto",
  "files": [
    {{"path": "index.html", "content": "...código completo..."}},
    {{"path": "README.md", "content": "# Nome\\nDescrição"}}
  ]
}}"""

    loop = asyncio.get_event_loop()
    code_response = await loop.run_in_executor(None, lambda: _call_claude_sonnet(PROMPTS["dev"], code_prompt, 8000))

    # Parse o JSON de resposta do Dev
    project_data = None
    try:
        # Extrai JSON da resposta (pode ter texto em volta)
        json_match = re.search(r'\{[\s\S]*\}', code_response)
        if json_match:
            project_data = json_lib.loads(json_match.group())
    except Exception as e:
        logger.error(f"[DEV] Falha ao parsear JSON: {e}\nResposta: {code_response[:200]}")

    if not project_data or not project_data.get("files"):
        await post_to_group("dev", "⚠️ Erro ao gerar o código. Vou tentar novamente com abordagem diferente.")
        # Segunda tentativa mais simples
        simple_prompt = f"Crie um site completo em HTML para: {pedido}. Retorne APENAS o JSON conforme o formato solicitado."
        code_response = await loop.run_in_executor(None, lambda: _call_claude_sonnet(PROMPTS["dev"], simple_prompt + "\n\n" + code_prompt, 8000))
        try:
            json_match = re.search(r'\{[\s\S]*\}', code_response)
            if json_match:
                project_data = json_lib.loads(json_match.group())
        except:
            pass

    if not project_data or not project_data.get("files"):
        await post_to_group("ceo", "❌ Não consegui gerar o código desta vez. Pode detalhar melhor o que quer?")
        return

    # 5. Sobe no GitHub
    if not GITHUB_TOKEN:
        await post_to_group("dev", "⚠️ GitHub token não configurado. O código foi criado mas não posso fazer o deploy.\n\nAdicione GITHUB_TOKEN nas variáveis de ambiente do Render.")
        # Mostra o código mesmo assim
        for f in project_data["files"][:1]:
            preview = f["content"][:500] + "..." if len(f["content"]) > 500 else f["content"]
            await post_to_group("dev", f"📄 `{f['path']}`:\n```\n{preview}\n```")
        return

    await post_to_group("dev", "📦 Subindo no GitHub...")

    try:
        repo_name = project_data.get("repo_name", "projeto-fazza")
        repo_desc = project_data.get("description", f"Projeto criado pelos agentes Fazza: {pedido[:80]}")
        files = project_data["files"]

        # Garante README
        if not any(f["path"].lower() == "readme.md" for f in files):
            files.append({"path": "README.md", "content": f"# {repo_name}\n\n{repo_desc}\n\nCriado pelos Agentes Fazza."})

        repo = await loop.run_in_executor(None, lambda: github_create_repo(repo_name, repo_desc))
        await asyncio.sleep(2)  # Aguarda repo inicializar
        await loop.run_in_executor(None, lambda: github_push_files(repo["full_name"], files))

        repo_url = repo["url"]
        await post_to_group("dev", f"✅ Código no GitHub: {repo_url}")

        # 6. Deploy (GitHub Pages para sites estáticos)
        has_index = any(f["path"] == "index.html" for f in files)
        if has_index:
            await post_to_group("dev", "🚀 Ativando deploy...")
            pages_url = await loop.run_in_executor(None, lambda: github_enable_pages(repo["full_name"]))
            await asyncio.sleep(3)

            # 7. CEO entrega o resultado
            final_msg = await agent_respond("ceo",
                f"O projeto '{repo_name}' foi criado e está no ar. GitHub: {repo_url} | Site: {pages_url}. Diga ao Vinicius que está pronto (pode levar 1-2min para o site ficar no ar).")
            await post_to_group("ceo", f"{final_msg}\n\n🌐 Site: {pages_url}\n📦 Código: {repo_url}")
        else:
            final_msg = await agent_respond("ceo",
                f"O projeto '{repo_name}' foi criado. GitHub: {repo_url}. Informe ao Vinicius que o código está disponível.")
            await post_to_group("ceo", f"{final_msg}\n\n📦 Código: {repo_url}")

    except Exception as e:
        logger.error(f"[PROJETO] Erro no deploy: {e}")
        await post_to_group("ceo", f"❌ Erro no deploy: {str(e)[:100]}\nO código foi criado mas o deploy falhou. Confere os tokens.")


# ============================================================
# FLUXO SIMPLES: CHAT / PERGUNTAS
# ============================================================
async def run_simple_chat(texto: str, nome: str):
    """Resposta rápida para mensagens de chat."""
    ctx = "\n".join([f"{m['name']}: {m['text']}" for m in historico[-6:]])

    # Roteamento + resposta em uma chamada (Haiku = rápido)
    route_prompt = f"""Você é um roteador. Analise a mensagem e retorne JSON:
{{"agent": "ceo|dev|lider|designer|financeiro", "response": "resposta curta em português (max 2 frases)"}}

Regras de roteamento: tecnico/codigo->dev | estrategia/negocio->ceo | tarefas/plano->lider | design/visual->designer | financeiro/roi->financeiro | geral->ceo

Contexto recente:
{ctx}

Mensagem de {nome}: {texto}

Retorne APENAS o JSON, sem texto adicional."""

    loop = asyncio.get_event_loop()
    raw = await loop.run_in_executor(None, lambda: _call_claude(route_prompt, texto, 200))

    try:
        # Limpa markdown se houver
        clean = re.sub(r'```json|```', '', raw).strip()
        data = json_lib.loads(clean)
        agent = data.get("agent", "ceo")
        response = data.get("response", "...")
        if agent not in apps:
            agent = "ceo"
    except Exception:
        agent = "ceo"
        response = raw[:200] if raw else "Entendido."

    await post_to_group(agent, response)
    historico.append({"role": "assistant", "name": agent, "text": response})


# ============================================================
# HANDLER PRINCIPAL
# ============================================================
async def handle_message(update: Update, context):
    if not update.message or not update.message.text:
        return
    if update.message.chat_id != GROUP_ID:
        return
    if update.message.from_user and update.message.from_user.is_bot:
        return

    texto = update.message.text
    nome = update.message.from_user.first_name if update.message.from_user else "Usuário"

    historico.append({"role": "user", "name": nome, "text": texto})
    if len(historico) > 30:
        historico.pop(0)

    logger.info(f"[MSG] {nome}: {texto[:80]}")

    if is_project_task(texto):
        asyncio.create_task(run_project_workflow(texto))
    else:
        asyncio.create_task(run_simple_chat(texto, nome))


# ============================================================
# LIFESPAN + APP
# ============================================================
@asynccontextmanager
async def lifespan(_: FastAPI):
    # Cria apps PTB
    for nome, token in TOKENS.items():
        app_ptb = Application.builder().updater(None).token(token).build()
        apps[nome] = app_ptb

    # Handler só no CEO
    apps["ceo"].add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Inicializa todos
    for app_ptb in apps.values():
        await app_ptb.initialize()
        await app_ptb.start()

    # Webhook só no CEO
    wh_url = f"{RENDER_URL}/webhook/ceo"
    await apps["ceo"].bot.set_webhook(url=wh_url, drop_pending_updates=True, allowed_updates=["message"])
    info = await apps["ceo"].bot.get_webhook_info()
    logger.info(f"[WEBHOOK] CEO: {info.url} | pending: {info.pending_update_count}")

    # Remove webhooks dos outros
    for nome in ["dev", "lider", "designer", "financeiro"]:
        await apps[nome].bot.delete_webhook(drop_pending_updates=True)
        logger.info(f"[SISTEMA] {nome} online (apenas envio)")

    logger.info("[SISTEMA] Time de agentes online. Prontos para tarefas complexas.")
    yield

    for app_ptb in apps.values():
        await app_ptb.stop()
        await app_ptb.shutdown()


fastapi_app = FastAPI(lifespan=lifespan)


@fastapi_app.get("/")
async def health():
    return {
        "status": "ok",
        "modo": "agentico",
        "llm": "claude-sonnet-4-6 + claude-haiku",
        "ferramentas": ["github_create_repo", "github_push_files", "github_pages"],
        "github": "configurado" if GITHUB_TOKEN else "ausente - adicione GITHUB_TOKEN",
        "anthropic": "configurado" if ANTHROPIC_KEY else "ausente - adicione ANTHROPIC_API_KEY"
    }


@fastapi_app.get("/webhook/info")
async def webhook_info():
    info = await apps["ceo"].bot.get_webhook_info()
    return {
        "ceo": {"url": info.url, "pending": info.pending_update_count, "last_error": info.last_error_message},
        "outros": "apenas envio, sem webhook"
    }


@fastapi_app.post("/webhook/ceo")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, apps["ceo"].bot)
    await apps["ceo"].process_update(update)
    return Response(status_code=HTTPStatus.OK)
