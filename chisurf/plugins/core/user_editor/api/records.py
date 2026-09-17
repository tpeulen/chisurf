"""User rows, the save payload, and the validation the form applies.

Validation deliberately mirrors what the backend enforces
(``mmfdb/admin/backend/services.py``) so the user is told *before* a round trip.
Where the two could drift, the backend wins -- these checks refuse early, they
never permit something the server would reject.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Roles the combo offers. It is editable, so a value stored by another tool is
#: preserved rather than collapsed into "Other" and saved back as that literal.
ROLE_OPTIONS = (
    "Generic",
    "Principal Investigator",
    "Postdoc",
    "PhD Student",
    "Master Student",
    "Bachelor Student",
    "Technician",
    "Engineer",
    "Collaborator",
    "Guest",
    "Other",
)

#: Accounts the backend refuses to rename or delete.
PROTECTED_USER_IDS = frozenset({"user_default", "guest"})


@dataclass
class UserRow:
    """One MMFDB user account."""

    user_id: str = ""
    user_uuid: str = ""
    display_name: str = ""
    email: str = ""
    role: str = "Generic"
    affiliation: str = ""
    department: str = ""
    phone: str = ""
    website: str = ""
    address: str = ""
    details: str = ""
    is_admin: bool = False
    allow_autologin: bool = False
    is_active: bool = False

    @classmethod
    def from_record(cls, record: dict[str, Any], active_id: str = "") -> UserRow:
        """Build a row from a server record, tolerating missing columns."""
        get = record.get
        return cls(
            user_id=str(get("user_id") or ""),
            user_uuid=str(get("user_uuid") or ""),
            display_name=str(get("display_name") or ""),
            email=str(get("email") or ""),
            role=str(get("role") or "Generic"),
            affiliation=str(get("affiliation") or ""),
            department=str(get("department") or ""),
            phone=str(get("phone") or ""),
            website=str(get("website") or ""),
            address=str(get("address") or ""),
            details=str(get("details") or ""),
            is_admin=bool(get("is_admin")),
            allow_autologin=bool(get("allow_passwordless_login")),
            is_active=str(get("user_id") or "") == active_id,
        )

    @property
    def protected(self) -> bool:
        """Whether the backend refuses to rename or delete this account."""
        return self.user_id in PROTECTED_USER_IDS

    def as_record(self) -> dict[str, Any]:
        """The row as a flat table record."""
        return {
            "user": self.display_name or self.user_id,
            "username": self.user_id,
            "role": self.role,
            "admin": "yes" if self.is_admin else "",
            "autologin": "yes" if self.allow_autologin else "",
            "active": "★" if self.is_active else "",
            "email": self.email,
        }


def validate_user(
    row: UserRow, *, existing: list[UserRow] | None = None, creating: bool = False
) -> list[str]:
    """Problems that would make a save fail, in the order they should be shown.

    Parameters
    ----------
    row : UserRow
        The edited account.
    existing : list of UserRow, optional
        The accounts already known, so a duplicate username is caught here
        rather than as a raw RPC error.
    creating : bool, optional
        Whether this is a new account.

    Returns
    -------
    list of str
        Empty when the account can be saved.

    """
    problems: list[str] = []
    user_id = row.user_id.strip()

    if not user_id:
        problems.append("A username is required.")
    elif user_id != row.user_id:
        problems.append("The username must not start or end with a space.")
    elif any(c.isspace() for c in user_id):
        problems.append("The username must not contain spaces.")

    if not row.display_name.strip():
        problems.append("A display name is required.")

    email = row.email.strip()
    if email and ("@" not in email or "." not in email.split("@")[-1]):
        problems.append(f"{email!r} is not a valid e-mail address.")

    website = row.website.strip()
    if website and not website.startswith(("http://", "https://")):
        problems.append("The website must start with http:// or https://.")

    if creating and user_id and existing:
        if any(u.user_id == user_id for u in existing):
            problems.append(f"A user called {user_id!r} already exists.")

    return problems


def to_payload(
    row: UserRow,
    *,
    old_user_id: str | None = None,
    password: str | None = None,
    requester_id: str = "",
) -> dict[str, Any]:
    """The ``mmfdb.users.save`` payload for *row*."""
    payload: dict[str, Any] = {
        "user_uuid": row.user_uuid or None,
        "user_id": row.user_id.strip(),
        "display_name": row.display_name.strip(),
        "email": row.email.strip() or None,
        "role": row.role,
        "affiliation": row.affiliation.strip() or None,
        "department": row.department.strip() or None,
        "phone": row.phone.strip() or None,
        "website": row.website.strip() or None,
        "address": row.address.strip() or None,
        "details": row.details.strip() or None,
        "is_admin": 1 if row.is_admin else 0,
        "allow_passwordless_login": 1 if row.allow_autologin else 0,
        "requester_id": requester_id,
    }
    if old_user_id and old_user_id != payload["user_id"]:
        payload["old_user_id"] = old_user_id
    if password is not None:
        payload["password"] = password
    return payload
