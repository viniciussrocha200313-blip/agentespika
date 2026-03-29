# Fazza AI Team — Agentes Telegram

Time de 5 agentes IA com personalidades distintas que operam num grupo do Telegram.
Um orquestrador invisivel analisa cada mensagem e roteia para o(s) agente(s) correto(s).

## Agentes

| Agente | Bot | Papel |
|--------|-----|-------|
| Viktor (CEO) | @fazza_ceo_bot | Estrategista — desafia ideias, pensa no ecossistema |
| Kai (Dev) | @fazza_dev_bot | Dev senior — entrega codigo real, nao teoria |
| Alex (Lider) | @fazza_lider_bot | PM — transforma caos em plano com proximos passos |
| Luna (Designer) | @fazza_designer_bot | UX/Copy — pensa na experiencia do usuario |
| Max (Financeiro) | @fazza_financeiro_bot | Analista — transforma intuicao em numero |

## Arquitetura

```
Mensagem do user
    ↓
Orquestrador (Claude API) → decide quem responde
    ↓
Agente(s) selecionado(s) (Claude API + system prompt unico)
    ↓
Bot(s) Telegram envia(m) resposta(s)
```

O orquestrador nunca fala no grupo — ele so roteia.
Cada agente tem seu proprio bot do Telegram e responde com sua personalidade.

## Setup

### 1. Clonar e instalar

```bash
git clone https://github.com/viniciussrocha200313-blip/agentespika.git
cd agentespika
pip install -r requirements.txt
```

### 2. Configurar .env

```bash
cp .env.example .env
# Preencher com suas chaves
```

### 3. Rodar

```bash
python main.py
```

### 4. No grupo Telegram

Envie `/start` para registrar o grupo. Depois eh so mandar mensagens normais.

## Comandos

| Comando | Descricao |
|---------|-----------|
| `/start` | Registra o grupo e ativa os agentes |
| `/ping` | Health check — mostra bots online e contexto |
| `/reset` | Limpa historico de contexto |

## Docker

```bash
docker-compose up -d
```

## Stack

- Python 3.12
- python-telegram-bot 21.x
- Anthropic Claude API
- Docker

## Estrutura

```
agentespika/
├── main.py                    # Ponto de entrada
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── src/
    ├── agents/
    │   ├── orchestrator.py    # Orquestrador — roteia mensagens
    │   └── prompts.py         # System prompts de cada agente
    ├── core/
    │   ├── config.py          # Configuracoes (pydantic-settings)
    │   └── logger.py          # Logger padronizado
    ├── memory/
    │   └── context.py         # Historico de conversa em memoria
    └── telegram/
        └── bot_manager.py     # Gerencia os 5 bots do Telegram
```
