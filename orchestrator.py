import google.generativeai as genai
import os

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

SYSTEM_PROMPT = """Você é o orquestrador silencioso do time de IA do Vinicius Souza.
Analise a mensagem e retorne APENAS o(s) nome(s) do(s) agente(s) que deve(m) responder.

Regras:
- Código, sistema, API, arquitetura, bug, deploy → dev
- Estratégia, negócio, decisão, crescimento, oportunidade → ceo
- Tarefas, plano, organização, prazo, próximos passos → lider
- Visual, copy, campanha, apresentação, comunicação, marca → designer
- Dinheiro, custo, ROI, preço, viabilidade, número → financeiro
- Técnico + estratégico → ceo,dev
- Estratégia + execução → ceo,lider
- Criativo + estratégico → ceo,designer
- Sem contexto claro → ceo

Responda APENAS com o nome. Nada mais. Jamais explique sua escolha.
Exemplos válidos: "dev" | "ceo" | "ceo,dev" | "lider" | "ceo,lider"
"""


class Orchestrator:
    def __init__(self):
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    async def route(self, message: str, history: list) -> str:
        try:
            context = "\n".join([
                f"{m['role']} ({m['name']}): {m['text']}"
                for m in history[-5:]
            ])
            prompt = f"{SYSTEM_PROMPT}\n\nHistórico recente:\n{context}\n\nMensagem atual: {message}"
            response = self.model.generate_content(prompt)
            result = response.text.strip().lower()
            valid = ["ceo", "dev", "lider", "designer", "financeiro"]
            parts = [p.strip() for p in result.split(",")]
            chosen = [p for p in parts if p in valid]
            return ",".join(chosen) if chosen else "ceo"
        except Exception as e:
            print(f"[ORQUESTRADOR][ERRO] {e}")
            return "ceo"
