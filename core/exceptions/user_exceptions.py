from __future__ import annotations


class UserNotFoundError(Exception):
    def __init__(self, user_id: int | str) -> None:
        self.user_id = user_id
        super().__init__(f"User not found: {user_id}")


class UserAlreadyExistsError(Exception):
    def __init__(self, external_id: str, platform: str) -> None:
        self.external_id = external_id
        self.platform = platform
        super().__init__(
            f"User already exists: external_id={external_id}, platform={platform}"
        )
