import google.generativeai as genai
import os

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


class BaseAgent:
    def __init__(self, name: str, system_prompt: str):
        self.name = name
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        self.system_prompt = system_prompt

    async def respond(self, message: str, history: list) -> str:
        try:
            context = "\n".join([
                f"{m['role']} ({m['name']}): {m['text']}"
                for m in history[-10:]
            ])
            full_prompt = f"{self.system_prompt}\n\nHistórico da conversa:\n{context}\n\nMensagem atual: {message}\n\nResponda agora:"
            response = self.model.generate_content(full_prompt)
            return response.text.strip()
        except Exception as e:
            print(f"[{self.name.upper()}][ERRO] {e}")
            return None
