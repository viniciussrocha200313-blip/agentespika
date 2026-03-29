"""
Sistema de memoria e contexto do grupo.
Mantém historico de mensagens para dar contexto aos agentes.
Cada agente recebe o historico recente da conversa antes de responder.
"""

import time
from dataclasses import dataclass, field


@dataclass
class Message:
    """Uma mensagem no historico"""
    role: str           # "user" ou nome do agente (ex: "Viktor")
    content: str        # Texto da mensagem
    timestamp: float = field(default_factory=time.time)
    agent_id: str = ""  # ID do agente que enviou (vazio se for do user)


class ConversationMemory:
    """
    Memoria de conversa do grupo.
    Armazena as ultimas N mensagens para dar contexto.
    Thread-safe com acesso simples (sem banco, tudo em memoria).
    """

    def __init__(self, max_messages: int = 20):
        self._messages: list[Message] = []
        self._max = max_messages

    def add(self, role: str, content: str, agent_id: str = "") -> None:
        """Adiciona mensagem ao historico"""
        msg = Message(role=role, content=content, agent_id=agent_id)
        self._messages.append(msg)

        # Mantém limite — remove as mais antigas
        if len(self._messages) > self._max:
            self._messages = self._messages[-self._max:]

    def get_history(self, limit: int | None = None) -> list[dict]:
        """
        Retorna historico formatado para o Claude API.
        Formato: [{"role": "user"|"assistant", "content": "..."}]
        """
        msgs = self._messages[-(limit or self._max):]
        history = []

        for msg in msgs:
            if msg.role == "user":
                history.append({
                    "role": "user",
                    "content": msg.content,
                })
            else:
                # Mensagens de agentes vao como assistant com prefixo do nome
                history.append({
                    "role": "assistant",
                    "content": f"[{msg.role}]: {msg.content}",
                })

        return history

    def get_context_summary(self) -> str:
        """Gera resumo do contexto recente para o orquestrador"""
        if not self._messages:
            return "Sem contexto anterior."

        recent = self._messages[-5:]
        lines = []
        for msg in recent:
            prefix = "Vinicius" if msg.role == "user" else msg.role
            # Trunca mensagens longas no resumo
            content = msg.content[:150]
            if len(msg.content) > 150:
                content += "..."
            lines.append(f"- {prefix}: {content}")

        return "Contexto recente:\n" + "\n".join(lines)

    def clear(self) -> None:
        """Limpa todo o historico"""
        self._messages.clear()

    @property
    def size(self) -> int:
        return len(self._messages)
