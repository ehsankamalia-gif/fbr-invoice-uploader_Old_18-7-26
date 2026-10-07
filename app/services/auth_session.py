"""Holds the logged-in desktop Staff/Admin account for the lifetime of this
running process - in-memory only, never persisted or shared across
processes."""
from typing import Optional, Set


class AuthSession:
    def __init__(self):
        self._staff_id: Optional[int] = None
        self._role: Optional[str] = None
        self._full_name: Optional[str] = None
        self._mobile_number: Optional[str] = None
        self._permissions: Set[str] = set()

    def login(self, *, staff_id: int, role: str, full_name: str,
              mobile_number: str, permissions: Set[str]) -> None:
        self._staff_id = staff_id
        self._role = role
        self._full_name = full_name
        self._mobile_number = mobile_number
        self._permissions = set(permissions)

    def logout(self) -> None:
        self._staff_id = None
        self._role = None
        self._full_name = None
        self._mobile_number = None
        self._permissions = set()

    def is_logged_in(self) -> bool:
        return self._staff_id is not None

    def current_staff_id(self) -> Optional[int]:
        return self._staff_id

    def current_role(self) -> Optional[str]:
        return self._role

    def current_full_name(self) -> Optional[str]:
        return self._full_name

    def current_mobile_number(self) -> Optional[str]:
        return self._mobile_number

    def is_admin(self) -> bool:
        return self._role == "ADMIN"

    def has_permission(self, module_code: str) -> bool:
        """Admins always have every module; Staff need an explicit grant."""
        if not self.is_logged_in():
            return False
        if self.is_admin():
            return True
        return module_code in self._permissions


auth_session = AuthSession()
