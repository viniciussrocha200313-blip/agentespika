# Fazza AI Team — Agentes Telegram

Time de 5 agentes IA com personalidades distintas operando num grupo do Telegram.
Orquestrador invisivel (Gemini Flash) analisa cada mensagem e roteia para o(s) agente(s) correto(s).

## Agentes

| Agente | Bot | Papel |
|--------|-----|-------|
| Viktor (CEO) | @fazza_ceo_bot | Estrategista — desafia ideias, pensa no ecossistema |
| Kai (Dev) | @fazza_dev_bot | Dev senior — entrega codigo real, nao teoria |
| Alex (Lider) | @fazza_lider_bot | PM — transforma caos em plano |
| Luna (Designer) | @fazza_designer_bot | UX/Copy — pensa na experiencia do usuario |
| Max (Financeiro) | @fazza_financeiro_bot | Analista — transforma intuicao em numero |

## Como funciona

```
Mensagem do user no grupo
    |
    v
Bot CEO (listener) recebe a mensagem
    |
    v
Orquestrador (Gemini Flash) → decide quem responde
    |
    v
Agente(s) selecionado(s) (Gemini Flash + system prompt unico)
    |
    v
Bot(s) correspondente(s) envia(m) resposta no grupo
```

## Comandos

| Comando | Descricao |
|---------|-----------|
| `/start` | Registra o grupo e ativa os agentes |
| `/ping` | Health check — mostra bots online e contexto |
| `/reset` | Limpa historico de contexto |

## Deploy (Fly.io)

```bash
fly launch --name fazza-agents --region gru --no-deploy
fly secrets set GEMINI_API_KEY=... TELEGRAM_GROUP_ID=... CEO_BOT_TOKEN=... ...
fly deploy
fly logs --tail
```

## Stack

- Python 3.11 + python-telegram-bot 20.7
- Google Gemini 2.0 Flash API
- Fly.io (regiao GRU)
