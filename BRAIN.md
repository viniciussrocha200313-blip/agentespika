# BRAIN — Fazza AI Team (Agentes Telegram)

> Documento de contexto completo do projeto. Leia antes de qualquer acao.

---

## STATUS ATUAL

- **Backend**: FUNCIONAL — Telegram recebe mensagens, orquestrador roteia, bots enviam
- **Problema bloqueante**: Gemini API key estourou cota free (limit: 0)
- **Decisao**: Migrar para OpenRouter (ainda precisa da API key)
- **Rodando**: Localmente na maquina do Vinicius (Windows 11)
- **Fly.io**: App criado (`fazza-agents`, regiao GRU) mas conta trial mata apos 5min — precisa cartao de credito ou migrar host

---

## O QUE JA FOI FEITO

### 1. Bots criados no BotFather
Todos os 5 bots foram criados via Telegram Web no BotFather:

| Agente | Nome | Username | Token |
|--------|------|----------|-------|
| Viktor (CEO) | Fazza CEO | @fazza_ceo_bot | `8739880872:AAFnttMx4qgx4cvdhkCODjK_QrQb4JTamj8` |
| Kai (Dev) | Fazza Dev | @fazza_dev_bot | `8765053219:AAEcmxtQwREzJb0p8OkXNdPjeO67OueeIq4` |
| Alex (Lider) | Fazza Lider | @fazza_lider_bot | `8731619108:AAH8v40Ci_o3hW-A-HRQIKPqovnwDBSBedc` |
| Luna (Designer) | Fazza Designer | @fazza_designer_bot | `8621042445:AAHMOn1q0Rec2KbZFJTJBfKbUbhcDaZny4k` |
| Max (Financeiro) | Fazza Financeiro | @fazza_financeiro_bot | `8695419311:AAHXFspEZYx8XhZKLp0S6B7nuxGvihOS_Ww` |

Tokens tambem salvos em `C:\Users\vinic\Desktop\bot_tokens.txt`

### 2. Grupo Telegram criado
- Nome: **Agentes**
- Group ID: **-5048431990**
- Membros: Vinicius R (owner) + 5 bots
- URL: https://t.me/+yZdprfg9iAg3OTkx

### 3. Backend implementado
Repositorio: `https://github.com/viniciussrocha200313-blip/agentespika.git`

Estrutura:
```
agentespika/
├── main.py              # Ponto de entrada — polling + handlers
├── orchestrator.py      # Roteia mensagens (atualmente Gemini, migrar pra OpenRouter)
├── agents/
│   ├── __init__.py
│   ├── base_agent.py    # Classe base — chama LLM com system prompt
│   ├── ceo.py           # Viktor — estrategista
│   ├── dev.py           # Kai — dev senior
│   ├── lider.py         # Alex — lider de projetos
│   ├── designer.py      # Luna — UX/copy/comunicacao
│   └── financeiro.py    # Max — analista financeiro
├── memory/
│   ├── __init__.py
│   └── history.py       # Historico em RAM (50 msgs max)
├── requirements.txt
├── Dockerfile
├── fly.toml
├── .env                 # NAO commitado (tem tokens)
├── .env.example
├── .gitignore
└── README.md
```

### 4. Deploy Fly.io (parcial)
- App: `fazza-agents`
- Regiao: GRU (Sao Paulo)
- Machine ID: `1850927a4019e8`
- Problema: conta trial mata apos 5 minutos
- Secrets ja configurados no Fly

### 5. Teste local confirmado
- Rodou `python main.py` localmente com sucesso
- Os 5 bots inicializaram e receberam mensagens do grupo
- Mensagens recebidas nos logs: "Agentes", "Opa", "Estao ai?"
- Falharam no orquestrador por cota da Gemini API

---

## PROXIMOS PASSOS (por ordem de prioridade)

### 1. Obter API key do OpenRouter
- Criar conta em openrouter.ai
- Gerar key (formato: `sk-or-v1-...`)
- Adicionar credito ou usar free tier

### 2. Migrar de Gemini para OpenRouter
Trocar `orchestrator.py` e `agents/base_agent.py` para usar OpenRouter via requests HTTP.
OpenRouter usa formato OpenAI-compatible:
```
POST https://openrouter.ai/api/v1/chat/completions
Headers: Authorization: Bearer sk-or-v1-...
Body: {"model": "google/gemini-2.0-flash-exp:free", "messages": [...]}
```
Modelos free recomendados no OpenRouter:
- `google/gemini-2.0-flash-exp:free`
- `meta-llama/llama-3.3-70b-instruct:free`

### 3. Corrigir encoding Windows
- Tem um `\u2192` (seta →) no print de roteamento que causa erro no Windows
- Substituir por `->` ou `->`

### 4. Resolver hosting
Opcoes:
- **Fly.io**: adicionar cartao de credito (plano free tem 3 VMs gratis)
- **Render**: plano free para workers sem limite de tempo
- **Railway**: $5 de credito gratis por mes
- **VPS Hostinger**: Vinicius ja tem VPS, pode rodar la

### 5. Testar end-to-end
- Mandar mensagem no grupo
- Confirmar que orquestrador roteia corretamente
- Confirmar que bot correto responde com personalidade certa

---

## ARQUITETURA — COMO FUNCIONA

```
Mensagem do user no grupo Telegram
         |
         v
Bot CEO (listener via polling) recebe update
         |
         v
Orquestrador (LLM call) analisa mensagem
  → retorna "ceo", "dev", "ceo,dev", etc
         |
         v
Para cada agente selecionado:
  → LLM call com system prompt unico + historico
  → Bot correspondente envia resposta no grupo
         |
         v
Resposta salva no historico (RAM, max 50 msgs)
```

**Importante**: Apenas o bot CEO faz polling. Os outros bots sao usados apenas para ENVIAR mensagens (cada um envia pelo seu proprio bot, assim aparece com nome diferente no grupo).

---

## SYSTEM PROMPTS (resumo)

### Orquestrador (invisivel)
Analisa mensagem e retorna APENAS o nome do agente. Regras de roteamento:
- Codigo/API/bug → dev
- Estrategia/negocio → ceo
- Tarefas/plano/prazo → lider
- Visual/copy/campanha → designer
- Dinheiro/custo/ROI → financeiro
- Sem contexto claro → ceo (fallback)

### Viktor (CEO)
Estrategista provocador. Desafia ideias. Termina com pergunta. Max 3-4 paragrafos.

### Kai (Dev)
Dev senior direto. Entrega codigo real, nao teoria. Seco quando necessario.

### Alex (Lider)
Transforma caos em plano. Sempre termina com "**Proximo passo:**". Usa listas.

### Luna (Designer)
UX/copy criativa com fundamento. Sempre inclui exemplo concreto. Max 4 paragrafos.

### Max (Financeiro)
Analitico sem vies emocional. Formato: Custo → Receita → ROI → Recomendacao.

(Prompts completos estao em cada arquivo: agents/ceo.py, agents/dev.py, etc)

---

## COMANDOS TELEGRAM

| Comando | O que faz |
|---------|-----------|
| `/start` | Registra group ID e ativa |
| `/ping` | Health check — bots online + msgs no contexto |
| `/reset` | Limpa historico de contexto |

---

## VARIAVEIS DE AMBIENTE (.env)

```
GEMINI_API_KEY=AIzaSyAFXqH_tKOvPQZ2hxKFWJ5XjDFKjLcCdPM   # ESTOUROU COTA
OPENROUTER_API_KEY=                                         # PENDENTE
TELEGRAM_GROUP_ID=-5048431990
CEO_BOT_TOKEN=8739880872:AAFnttMx4qgx4cvdhkCODjK_QrQb4JTamj8
DEV_BOT_TOKEN=8765053219:AAEcmxtQwREzJb0p8OkXNdPjeO67OueeIq4
LIDER_BOT_TOKEN=8731619108:AAH8v40Ci_o3hW-A-HRQIKPqovnwDBSBedc
DESIGNER_BOT_TOKEN=8621042445:AAHMOn1q0Rec2KbZFJTJBfKbUbhcDaZny4k
FINANCEIRO_BOT_TOKEN=8695419311:AAHXFspEZYx8XhZKLp0S6B7nuxGvihOS_Ww
```

---

## ERROS CONHECIDOS E SOLUCOES

| Erro | Causa | Solucao |
|------|-------|---------|
| `429 quota exceeded` Gemini | Key free sem credito | Migrar pra OpenRouter |
| `charmap codec can't encode \u2192` | Caractere → no Windows cp1252 | Trocar por `->` |
| `Conflict: terminated by other getUpdates` | 2 instancias do mesmo bot rodando | Garantir apenas 1 processo |
| Fly.io mata apos 5min | Conta trial sem cartao | Adicionar cartao ou trocar host |
| `UnicodeEncodeError` com emojis | Emojis em print() no Windows | Remover emojis dos prints |

---

## CONTEXTO DO USUARIO

- **Nome**: Vinicius Souza
- **Papel**: Braco direito do CEO da VR Holding / Fazza Marketing
- **Nivel tecnico**: Iniciante em codigo
- **SO principal**: Windows 11 (D:\AI_WORK) — tambem usa Mac
- **GitHub**: viniciussrocha200313-blip (conta ativa pra push)
- **Outra conta GitHub**: centralfazza (precisa `gh auth switch` antes de push)
- **Projetos**: Fazza Hub, Fazza Automation, Jarvis, VR Holding

---

## GIT — NOTAS

- Repositorio: https://github.com/viniciussrocha200313-blip/agentespika.git
- Branch: main
- Para push funcionar: `gh auth switch --user viniciussrocha200313-blip` primeiro
- O `.env` NAO eh commitado (tem tokens reais)
- O `BRAIN.md` EH commitado (referencia do projeto)
