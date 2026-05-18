"""Common base class for all backend clients."""


class BaseClient:
    """Subclasses must implement query(prompt, model) -> str."""

    def query(self, prompt: str, model: str) -> str:
        raise NotImplementedError("query() must be implemented in subclass")
