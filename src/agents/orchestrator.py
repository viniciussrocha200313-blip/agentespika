"""
Orquestrador — o cerebro invisivel do time.
Recebe a mensagem do usuario, consulta Claude para decidir
qual(is) agente(s) deve(m) responder, e despacha.
"""

import anthropic

from src.agents.prompts import ORCHESTRATOR_PROMPT, AGENT_PROMPTS, AGENT_NAMES
from src.core.config import settings
from src.core.logger import log
from src.memory.context import ConversationMemory


class Orchestrator:
    """
    Fluxo:
    1. Recebe mensagem do user
    2. Chama Claude com prompt do orquestrador → retorna "ceo", "dev", "ceo,dev" etc
    3. Para cada agente selecionado, chama Claude com o prompt do agente + historico
    4. Retorna as respostas prontas para envio no Telegram
    """

    def __init__(self):
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._memory = ConversationMemory(max_messages=settings.max_history_messages)
        self._model = settings.claude_model
        log.info("Orquestrador inicializado — modelo: %s", self._model)

    async def route(self, user_message: str) -> list[str]:
        """
        Decide quais agentes devem responder.
        Retorna lista de IDs: ["ceo"], ["ceo", "dev"], etc.
        """
        context = self._memory.get_context_summary()
        routing_input = f"{context}\n\nMensagem atual: {user_message}"

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=50,
                system=ORCHESTRATOR_PROMPT,
                messages=[{"role": "user", "content": routing_input}],
            )

            raw = response.content[0].text.strip().lower()
            agents = [a.strip() for a in raw.split(",") if a.strip() in AGENT_PROMPTS]

            if not agents:
                log.warning("Orquestrador retornou '%s' — fallback para ceo", raw)
                agents = ["ceo"]

            log.info("Roteamento: '%s' → %s", user_message[:60], agents)
            return agents

        except Exception as e:
            log.error("Erro no roteamento: %s — fallback para ceo", e)
            return ["ceo"]

    async def get_agent_response(self, agent_id: str, user_message: str) -> str:
        """
        Gera resposta de um agente especifico usando Claude.
        Inclui historico da conversa como contexto.
        """
        system_prompt = AGENT_PROMPTS[agent_id]
        history = self._memory.get_history()

        # Adiciona a mensagem atual ao final
        messages = history + [{"role": "user", "content": user_message}]

        # Garante que a lista nao comece com assistant
        if messages and messages[0]["role"] == "assistant":
            messages = messages[1:]

        # Garante alternancia user/assistant (Claude API exige)
        messages = self._fix_message_alternation(messages)

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=settings.max_tokens_response,
                system=system_prompt,
                messages=messages,
            )

            text = response.content[0].text.strip()
            agent_name = AGENT_NAMES[agent_id]

            log.info(
                "Resposta de %s (%s): %d chars, %d tokens input, %d tokens output",
                agent_name,
                agent_id,
                len(text),
                response.usage.input_tokens,
                response.usage.output_tokens,
            )

            return text

        except Exception as e:
            log.error("Erro ao gerar resposta de %s: %s", agent_id, e)
            return f"⚠️ Erro interno ao processar com {AGENT_NAMES[agent_id]}."

    async def process_message(self, user_message: str) -> dict[str, str]:
        """
        Pipeline completo:
        1. Roteia a mensagem
        2. Gera resposta de cada agente selecionado
        3. Salva no historico
        4. Retorna {agent_id: resposta}
        """
        # Salva mensagem do user no historico
        self._memory.add(role="user", content=user_message)

        # Roteamento
        selected_agents = await self.route(user_message)

        # Gera respostas
        responses: dict[str, str] = {}
        for agent_id in selected_agents:
            response_text = await self.get_agent_response(agent_id, user_message)
            responses[agent_id] = response_text

            # Salva resposta no historico
            agent_name = AGENT_NAMES[agent_id]
            self._memory.add(
                role=agent_name,
                content=response_text,
                agent_id=agent_id,
            )

        return responses

    @staticmethod
    def _fix_message_alternation(messages: list[dict]) -> list[dict]:
        """
        Claude API exige alternancia user/assistant.
        Se duas mensagens consecutivas tem o mesmo role, junta em uma so.
        """
        if not messages:
            return [{"role": "user", "content": "Olá"}]

        fixed = [messages[0]]
        for msg in messages[1:]:
            if msg["role"] == fixed[-1]["role"]:
                # Junta com a anterior
                fixed[-1]["content"] += "\n\n" + msg["content"]
            else:
                fixed.append(msg)

        # Garante que termina com user
        if fixed[-1]["role"] != "user":
            fixed.append({"role": "user", "content": "Continue."})

        return fixed
