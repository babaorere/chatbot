class BusinessConfigNotFoundError(Exception):
    def __init__(self, message: str = "Business configuration not found") -> None:
        self.message = message
        super().__init__(self.message)
