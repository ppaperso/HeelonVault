"""Types liés aux informations d'utilisateur authentifié."""

from typing import NotRequired, TypedDict


class UserInfo(TypedDict):
    """Informations d'utilisateur propagées dans le flux d'authentification."""

    username: str
    email: NotRequired[str]
    role: NotRequired[str]
    workspace_uuid: NotRequired[str]
    totp_enabled: NotRequired[bool]
    totp_confirmed: NotRequired[bool]
    last_login: NotRequired[str | None]
    avatar_path: NotRequired[str | None]
    language: NotRequired[str]

class UserInfoUpdate(TypedDict, total=False):
    """Mises à jour partielles d'un utilisateur."""
    username: str
    email: str
    role: str
    workspace_uuid: str
    totp_enabled: bool
    totp_confirmed: bool
    last_login: str | None
    avatar_path: str | None
    language: str
