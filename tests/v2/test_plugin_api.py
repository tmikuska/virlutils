import types

import click
import pytest

from virl.api import plugin


def test_load_plugins_only_adds_real_directories(monkeypatch):
    monkeypatch.setattr(plugin, "iter_modules", lambda path: [])
    monkeypatch.setattr(plugin.os.path, "isdir", lambda p: p == "/tmp/real-plugin-dir")
    fake_syspath = []
    monkeypatch.setattr(plugin.sys, "path", fake_syspath)

    plugin.load_plugins("/tmp/real-plugin-dir:/tmp/missing-plugin-dir")

    assert fake_syspath == ["/tmp/real-plugin-dir"]


def test_load_plugins_reports_invalid_plugin_import(monkeypatch):
    monkeypatch.setattr(plugin.os.path, "isdir", lambda _p: False)
    monkeypatch.setattr(
        plugin,
        "iter_modules",
        lambda path: [types.SimpleNamespace(name="broken_plugin")],
    )

    def _raise_import_error(name):
        raise ImportError("boom")

    monkeypatch.setattr(plugin, "import_module", _raise_import_error)

    reported = []
    monkeypatch.setattr(plugin.click, "secho", lambda msg, fg: reported.append((msg, fg)))

    plugin.load_plugins(["/not/used"])

    assert reported == [("boom", "red")]


def test_plugin_base_raises_for_unsupported_and_disabled():
    plugin._test_enable_plugins(enabled=True)
    with pytest.raises(ValueError):
        plugin.Plugin()

    plugin._test_enable_plugins(enabled=False)
    try:
        with pytest.raises(plugin.NoPluginError):
            plugin.Plugin(command="anything")
    finally:
        plugin._test_enable_plugins(enabled=True)


def test_check_valid_plugin_and_abstract_methods():
    plugin._test_enable_plugins(enabled=True)

    class LocalCommand(plugin.CommandPlugin, command="local-cmd"):
        @staticmethod
        @click.command()
        def run():
            return None

    class LocalGenerator(plugin.GeneratorPlugin, generator="local-gen"):
        @staticmethod
        @click.command()
        def generate():
            return None

    class LocalViewer(plugin.ViewerPlugin, viewer="local-view"):
        def visualize(self, **kwargs):
            return kwargs

    cmd = plugin.CommandPlugin(command="local-cmd")
    gen = plugin.GeneratorPlugin(generator="local-gen")
    view = plugin.ViewerPlugin(viewer="local-view")

    assert cmd.command == "local-cmd"
    assert gen.generator == "local-gen"
    assert view.viewer == "local-view"
    assert plugin.check_valid_plugin(cmd, cmd.run, "run") is True
    assert plugin.check_valid_plugin(view, view.visualize, "visualize", is_click=False) is True
    assert plugin.check_valid_plugin(view, view.visualize, "visualize", is_click=True) is False

    with pytest.raises(NotImplementedError):
        plugin.CommandPlugin.run.callback()
    with pytest.raises(NotImplementedError):
        plugin.GeneratorPlugin.generate.callback()
    with pytest.raises(NotImplementedError):
        plugin.ViewerPlugin.visualize(None)


def test_plugin_subclass_validation_errors():
    plugin._test_enable_plugins(enabled=True)

    try:
        with pytest.raises(ValueError):
            type(
                "DualTypePlugin",
                (plugin.Plugin,),
                {"__module__": __name__},
                command="dual-test-cmd",
                generator="dual-test-gen",
            )
    finally:
        plugin.Plugin.remove_plugin("command", "dual-test-cmd")
        plugin.Plugin.remove_plugin("generator", "dual-test-gen")

    with pytest.raises(ValueError):
        type(
            "InvalidPlugin",
            (plugin.Plugin,),
            {"__module__": __name__},
        )
