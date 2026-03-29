class History:
    def __init__(self, max_size: int = 50):
        self.messages = []
        self.max_size = max_size

    def add(self, role: str, name: str, text: str):
        self.messages.append({"role": role, "name": name, "text": text})
        if len(self.messages) > self.max_size:
            self.messages = self.messages[-self.max_size:]

    def get(self) -> list:
        return self.messages.copy()
