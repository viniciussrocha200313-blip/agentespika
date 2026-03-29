import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from orchestrator import Orchestrator
from agents.ceo import CeoAgent
from agents.dev import DevAgent
from agents.lider import LiderAgent
from agents.designer import DesignerAgent
from agents.financeiro import FinanceiroAgent
from memory.history import History

history = History()
orchestrator = Orchestrator()

agents = {
    "ceo": CeoAgent(),
    "dev": DevAgent(),
    "lider": LiderAgent(),
    "designer": DesignerAgent(),
    "financeiro": FinanceiroAgent(),
}

GROUP_ID = int(os.getenv("TELEGRAM_GROUP_ID", "0"))

# Mapa de tokens para criar os bots que enviam mensagens
BOT_TOKENS = {
    "ceo": os.getenv("CEO_BOT_TOKEN"),
    "dev": os.getenv("DEV_BOT_TOKEN"),
    "lider": os.getenv("LIDER_BOT_TOKEN"),
    "designer": os.getenv("DESIGNER_BOT_TOKEN"),
    "financeiro": os.getenv("FINANCEIRO_BOT_TOKEN"),
}

# Bots individuais para enviar respostas (inicializados no startup)
send_bots = {}

processing = False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global processing

    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id

    # Aceita mensagens do grupo configurado ou de qualquer grupo se GROUP_ID == 0
    if GROUP_ID != 0 and chat_id != GROUP_ID:
        return

    sender = update.message.from_user
    if sender and sender.is_bot:
        return

    # Evita processar multiplas mensagens ao mesmo tempo
    if processing:
        return

    processing = True
    text = update.message.text
    username = sender.username or sender.first_name if sender else "User"

    print(f"[MSG] {username}: {text}")

    try:
        history.add("user", username, text)

        # Orquestrador decide quem responde
        chosen = await orchestrator.route(text, history.get())
        agent_names = [a.strip() for a in chosen.split(",")]

        print(f"[ROTEAMENTO] {text[:60]} -> {agent_names}")

        for agent_name in agent_names:
            if agent_name not in agents:
                continue

            agent = agents[agent_name]
            response = await agent.respond(text, history.get())

            if response:
                history.add("assistant", agent_name, response)

                # Envia pelo bot correspondente
                bot = send_bots.get(agent_name)
                if bot:
                    # Divide mensagens longas (limite Telegram: 4096)
                    chunks = split_message(response)
                    for chunk in chunks:
                        try:
                            await bot.send_message(
                                chat_id=chat_id,
                                text=chunk,
                                parse_mode="Markdown"
                            )
                        except Exception:
                            # Fallback sem parse_mode se Markdown falhar
                            await bot.send_message(
                                chat_id=chat_id,
                                text=chunk
                            )
                        if len(chunks) > 1:
                            await asyncio.sleep(0.5)

                print(f"[{agent_name.upper()}] Respondeu ({len(response)} chars)")

                # Delay entre agentes
                if len(agent_names) > 1:
                    await asyncio.sleep(1)

    except Exception as e:
        print(f"[ERRO] {e}")
    finally:
        processing = False


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GROUP_ID
    chat = update.effective_chat
    if chat:
        GROUP_ID = chat.id
        print(f"[INFO] Group ID registrado: {GROUP_ID}")
        await update.message.reply_text(
            f"[OK] Fazza AI Team ativo.\n"
            f"Group ID: `{GROUP_ID}`\n\n"
            f"Envie qualquer mensagem e o time responde.",
            parse_mode="Markdown"
        )


async def handle_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bots_online = len(send_bots)
    msgs = len(history.get())
    await update.message.reply_text(
        f"Pong!\n"
        f"Bots online: {bots_online}/5\n"
        f"Mensagens no contexto: {msgs}"
    )


async def handle_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history.messages.clear()
    await update.message.reply_text("Contexto limpo. Comecando do zero.")
    print("[INFO] Historico limpo por /reset")


def split_message(text: str, max_length: int = 4000) -> list:
    if len(text) <= max_length:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        split_pos = text.rfind("\n\n", 0, max_length)
        if split_pos == -1:
            split_pos = text.rfind("\n", 0, max_length)
        if split_pos == -1:
            split_pos = text.rfind(" ", 0, max_length)
        if split_pos == -1:
            split_pos = max_length
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip()

    return chunks


async def main():
    print("=" * 50)
    print("FAZZA AI TEAM - Iniciando")
    print("=" * 50)

    # Cria Application para cada bot
    apps = {}
    for name, token in BOT_TOKENS.items():
        if not token:
            print(f"[WARN] Token do bot {name} nao configurado")
            continue
        app = Application.builder().token(token).build()
        apps[name] = app

    # Inicializa todas as apps e guarda os bots para envio
    for name, app in apps.items():
        await app.initialize()
        send_bots[name] = app.bot
        bot_info = await app.bot.get_me()
        print(f"[INFO] Bot {name} inicializado: @{bot_info.username}")

    # Adiciona handlers apenas no bot do CEO (listener principal)
    ceo_app = apps.get("ceo")
    if not ceo_app:
        print("[ERRO] Bot CEO nao configurado - impossivel continuar")
        return

    ceo_app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
        handle_message
    ))
    ceo_app.add_handler(CommandHandler("start", handle_start))
    ceo_app.add_handler(CommandHandler("ping", handle_ping))
    ceo_app.add_handler(CommandHandler("reset", handle_reset))

    # Limpa webhook anterior e inicia polling
    await ceo_app.bot.delete_webhook(drop_pending_updates=True)
    print("[INFO] Webhook limpo")

    await ceo_app.start()
    await ceo_app.updater.start_polling(
        drop_pending_updates=True,
        allowed_updates=["message"]
    )

    print(f"[INFO] Group ID: {GROUP_ID}")
    print("[ONLINE] Fazza AI Team rodando - aguardando mensagens")

    # Mantém rodando indefinidamente
    import signal

    stop = False

    def handle_signal(signum, frame):
        nonlocal stop
        print(f"[INFO] Sinal {signum} recebido - desligando...")
        stop = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    while not stop:
        await asyncio.sleep(5)

    print("[INFO] Desligando bots...")
    try:
        await ceo_app.updater.stop()
        await ceo_app.stop()
        await ceo_app.shutdown()
        for name, app in apps.items():
            if name != "ceo":
                await app.shutdown()
    except Exception as e:
        print(f"[WARN] Erro ao desligar: {e}")
    print("[INFO] Todos os bots desligados")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("[INFO] Desligado")
