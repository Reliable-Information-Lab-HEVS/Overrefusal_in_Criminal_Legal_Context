"""Common base class for model backends."""


class BaseClient:
    """Subclasses must implement query(prompt, model) -> str.

    On any failure, return a string starting with "[ERROR]" rather than
    raising, so a single bad call never aborts a long run.
    """

    def query(self, prompt: str, model: str) -> str:
        raise NotImplementedError
