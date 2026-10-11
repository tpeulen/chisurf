"""Run registry-provided commands to verify names, ownership and failure isolation."""

from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from chisurf.core.plugin.manifest import PluginManifest
from chisurf.core.plugin.registry import PluginRegistry


class _Loader:
    def __init__(self, targets):
        self.targets = targets
        self.loaded = []

    def load(self, entrypoint: str):
        self.loaded.append(entrypoint)
        target = self.targets[entrypoint]
        if isinstance(target, Exception):
            raise target
        return target


def _manifest(plugin_id, entrypoint):
    return PluginManifest.from_dict(
        {"id": plugin_id, "version": "1", "entrypoints": {"cli": entrypoint}}
    )


@pytest.mark.parametrize("entrypoint", ["public-alias=example:command", "example:command"])
def test_manifest_command_name_is_authoritative(entrypoint):
    @click.command(name="implementation-detail")
    def command():
        click.echo("executed plugin")

    group = click.Group()
    loader = _Loader({"example:command": command})
    registry = PluginRegistry(loader)
    registry._manifests = {"plugin_id": _manifest("plugin_id", entrypoint)}
    registry.register_cli(group)
    name = "public-alias" if "=" in entrypoint else "plugin-id"
    assert list(group.commands) == [name]
    result = CliRunner().invoke(group, [name])
    assert result.exit_code == 0, result.output
    assert result.output == "executed plugin\n"


@pytest.mark.parametrize("central", [False, True])
def test_command_collision_keeps_first_owner_and_does_not_import_loser(caplog, central):
    @click.command(name="same-name")
    def first():
        click.echo("first owner")

    @click.command(name="same-name")
    def second():
        click.echo("second owner")

    group = click.Group()
    if central:
        group.add_command(first, "same-name")
    loader = _Loader({"first:cli": first, "second:cli": second})
    registry = PluginRegistry(loader)
    registry._manifests = {
        "first": _manifest("first", "same-name=first:cli"),
        "second": _manifest("second", "same-name=second:cli"),
    }
    registry.register_cli(group)
    registry.register_cli(group)
    result = CliRunner().invoke(group, ["same-name"])
    assert result.exit_code == 0
    assert result.output == "first owner\n"
    assert loader.loaded == ([] if central else ["first:cli"])
    assert "same-name" in caplog.text and "second" in caplog.text


@pytest.mark.parametrize("broken_spec", ["=broken:cli", "bad=broken:cli"])
def test_failed_command_does_not_hide_healthy_sibling(broken_spec, caplog):
    @click.command()
    def healthy():
        click.echo("healthy")

    loader = _Loader({"broken:cli": ImportError("missing dependency"), "healthy:cli": healthy})
    registry = PluginRegistry(loader)
    registry._manifests = {
        "broken": _manifest("broken", broken_spec),
        "healthy": _manifest("healthy", "healthy=healthy:cli"),
    }
    group = click.Group()
    registry.register_cli(group)
    result = CliRunner().invoke(group, ["healthy"])
    assert result.exit_code == 0
    assert result.output == "healthy\n"
    assert list(group.commands) == ["healthy"]
    assert "broken" in caplog.text


@pytest.mark.parametrize("failure", ["raise", "core-collision", "duplicate-in-plugin"])
def test_service_registration_is_all_or_nothing(failure, caplog):
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    dispatcher = ServiceDispatcher(SessionState())
    dispatcher.register("core.ping", lambda _: {"ok": True, "result": "original"})

    def broken(registry):
        registry.register("broken.partial", lambda _: {"ok": True})
        if failure == "raise":
            raise RuntimeError("registrar failed after one method")
        if failure == "core-collision":
            registry.register("core.ping", lambda _: {"ok": True, "result": "stolen"})
        else:
            registry.register("broken.partial", lambda _: {"ok": True, "result": "duplicate"})

    def healthy(registry):
        registry.register("healthy.ping", lambda _: {"ok": True, "result": "healthy"})

    loader = _Loader({"broken:register": broken, "healthy:register": healthy})
    registry = PluginRegistry(loader)
    registry._manifests = {
        name: PluginManifest.from_dict(
            {
                "id": name,
                "version": "1",
                "entrypoints": {"services": f"{name}:register"},
            }
        )
        for name in ("broken", "healthy")
    }
    registry.register_services(dispatcher)
    assert dispatcher.list_methods() == ["core.ping", "healthy.ping"]
    assert dispatcher.dispatch("core.ping")["result"] == "original"
    assert dispatcher.dispatch("healthy.ping")["result"] == "healthy"
    assert not dispatcher.dispatch("broken.partial")["ok"]
    assert "broken" in caplog.text


def test_staged_services_are_visible_only_to_registering_thread():
    from concurrent.futures import ThreadPoolExecutor

    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    dispatcher = ServiceDispatcher(SessionState())
    dispatcher.register("core.ping", lambda _: {"ok": True})
    with dispatcher.registration_transaction("sample"):
        dispatcher.register("sample.ping", lambda _: {"ok": True, "result": "staged"})
        assert dispatcher.has_method("sample.ping")
        assert dispatcher.list_methods() == ["core.ping", "sample.ping"]
        assert dispatcher.dispatch("sample.ping")["result"] == "staged"
        with ThreadPoolExecutor(max_workers=1) as executor:
            assert not executor.submit(dispatcher.has_method, "sample.ping").result(timeout=5)
            assert executor.submit(dispatcher.list_methods).result(timeout=5) == ["core.ping"]
            assert not executor.submit(dispatcher.dispatch, "sample.ping").result(timeout=5)["ok"]
    assert dispatcher.has_method("sample.ping")
    assert dispatcher.dispatch("sample.ping")["result"] == "staged"


def test_transaction_rechecks_concurrent_collision_at_commit():
    from concurrent.futures import ThreadPoolExecutor

    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    dispatcher = ServiceDispatcher(SessionState())
    with pytest.raises(ValueError, match="sample"):
        with dispatcher.registration_transaction("sample"):
            dispatcher.register("sample.first", lambda _: {"ok": True})
            dispatcher.register("shared.ping", lambda _: {"ok": True, "result": "staged"})
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(
                    dispatcher.register,
                    "shared.ping",
                    lambda _: {"ok": True, "result": "concurrent"},
                ).result(timeout=5)
    assert dispatcher.list_methods() == ["shared.ping"]
    assert dispatcher.dispatch("shared.ping")["result"] == "concurrent"
    with dispatcher.registration_transaction("healthy"):
        dispatcher.register("healthy.ping", lambda _: {"ok": True})
    assert dispatcher.has_method("healthy.ping")


def test_nested_transaction_rejection_does_not_corrupt_outer_transaction():
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    dispatcher = ServiceDispatcher(SessionState())
    with dispatcher.registration_transaction("outer"):
        dispatcher.register("outer.ping", lambda _: {"ok": True})
        with pytest.raises(RuntimeError, match="Nested"):
            with dispatcher.registration_transaction("inner"):
                pass
    assert dispatcher.list_methods() == ["outer.ping"]


def test_direct_core_registration_preserves_explicit_replacement_behavior():
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    dispatcher = ServiceDispatcher(SessionState())
    dispatcher.register("core.ping", lambda _: {"ok": True, "result": "old"})
    dispatcher.register("core.ping", lambda _: {"ok": True, "result": "new"})
    assert dispatcher.dispatch("core.ping")["result"] == "new"


def test_legacy_duck_typed_dispatcher_still_receives_registration():
    class LegacyDispatcher:
        def __init__(self):
            self.methods = {}

        def register(self, name, handler):
            self.methods[name] = handler

    def register(dispatcher):
        dispatcher.register("legacy.ping", lambda _: {"ok": True})

    registry = PluginRegistry(_Loader({"legacy:register": register}))
    registry._manifests = {
        "legacy": PluginManifest.from_dict(
            {
                "id": "legacy",
                "version": "1",
                "entrypoints": {"services": "legacy:register"},
            }
        )
    }
    dispatcher = LegacyDispatcher()
    registry.register_services(dispatcher)
    assert dispatcher.methods["legacy.ping"]({}) == {"ok": True}


def test_caught_rpc_collision_still_aborts_transaction():
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    dispatcher = ServiceDispatcher(SessionState())
    dispatcher.register("core.ping", lambda _: {"ok": True})
    with pytest.raises(ValueError, match="core.ping"):
        with dispatcher.registration_transaction("sample"):
            dispatcher.register("sample.partial", lambda _: {"ok": True})
            try:
                dispatcher.register("core.ping", lambda _: {"ok": False})
            except ValueError:
                pass
    assert dispatcher.list_methods() == ["core.ping"]


def test_staged_falsey_callable_still_dispatches():
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    class Handler:
        def __bool__(self):
            return False

        def __call__(self, params):
            return {"ok": True, "result": "callable, not missing"}

    dispatcher = ServiceDispatcher(SessionState())
    with dispatcher.registration_transaction("sample"):
        dispatcher.register("sample.ping", Handler())
        assert dispatcher.dispatch("sample.ping") == {"ok": True, "result": "callable, not missing"}
