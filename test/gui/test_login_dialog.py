import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chisurf.gui import LoginDialog, QtWidgets, _format_login_error, dialogs


def test_format_login_error_extracts_jsonrpc_message() -> None:
    error = {
        "code": -32603,
        "message": "Invalid credentials",
        "data": {"error_code": "INTERNAL_ERROR", "exception_type": "AuthError"},
    }

    assert _format_login_error(error) == "Invalid credentials"


def test_format_login_error_extracts_service_error() -> None:
    error = {
        "ok": False,
        "error": "Authentication required",
        "error_code": "INTERNAL_ERROR",
    }

    assert _format_login_error(error) == "Authentication required"


def test_format_login_error_returns_string_for_unknown_structures() -> None:
    error = {"unexpected": {"nested": ["value"]}}

    assert _format_login_error(error) == '{"unexpected": {"nested": ["value"]}}'


def test_handle_login_sends_string_to_warning(monkeypatch) -> None:
    warning_calls = []

    def fake_warning(parent, title, text):
        warning_calls.append((parent, title, text))

    monkeypatch.setattr(dialogs.ChiSurfMessageBox, "warning", fake_warning)
    dialog = SimpleNamespace(
        user_combo=SimpleNamespace(currentData=lambda: "user_default"),
        password_edit=SimpleNamespace(text=lambda: "bad-password"),
        client=SimpleNamespace(
            login=lambda **_: {
                "error": {
                    "code": -32603,
                    "message": "Invalid credentials",
                    "data": {"exception_type": "AuthError"},
                }
            }
        ),
    )

    LoginDialog.handle_login(dialog)

    assert warning_calls == [(dialog, "Login Failed", "Invalid credentials")]


def test_handle_login_accepts_an_editable_username(monkeypatch) -> None:
    login_calls = []

    def fake_warning(*_args):
        return None

    monkeypatch.setattr(dialogs.ChiSurfMessageBox, "warning", fake_warning)
    dialog = SimpleNamespace(
        user_combo=SimpleNamespace(
            currentData=lambda: None,
            currentText=lambda: "admin",
        ),
        password_edit=SimpleNamespace(text=lambda: "admin"),
        client=SimpleNamespace(
            login=lambda **params: login_calls.append(params) or {"error": "test stop"}
        ),
    )

    LoginDialog.handle_login(dialog)

    assert login_calls == [{"user_id": "admin", "password": "admin"}]
