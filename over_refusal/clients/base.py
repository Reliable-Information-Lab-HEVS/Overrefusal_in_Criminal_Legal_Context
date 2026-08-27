"""Common base class for all backend clients."""


class BaseClient:
    """Subclasses must implement query(prompt, model, num_ctx=None) -> str."""

    def query(self, prompt: str, model: str, num_ctx: int = None) -> str:
        raise NotImplementedError("query() must be implemented in subclass")
