import importlib
import types

import pytest


def _load_main(monkeypatch):
    import virl.api
    import virl.helpers
    import virl.cli.generate
    import virl.api.plugin

    monkeypatch.setattr(virl.api, "VIRLServer", lambda: types.SimpleNamespace(config={}))
    monkeypatch.setattr(virl.helpers, "get_cml_client", lambda _s: types.SimpleNamespace(system_info=lambda: {"version": "2.5.0"}))
    monkeypatch.setattr(virl.api.plugin, "load_plugins", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(virl.api.plugin.Plugin, "get_plugins", lambda _kind: [])
    monkeypatch.setattr(virl.cli.generate, "init_generators", lambda: None)

    import virl.cli.main as main_mod

    return importlib.reload(main_mod)


def test_catch_all_exceptions_non_debug(monkeypatch):
    main_mod = _load_main(monkeypatch)
    group = main_mod.CatchAllExceptions(name="virl-test")
    monkeypatch.setattr(group, "main", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(main_mod, "get_command", lambda: "virl")
    monkeypatch.setattr(main_mod.click, "secho", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_mod.traceback, "format_exc", lambda: "trace")
    monkeypatch.setattr("builtins.exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
    main_mod.virl.debug = False
    with pytest.raises(SystemExit):
        group()


def test_catch_all_exceptions_debug_and_callback(monkeypatch):
    main_mod = _load_main(monkeypatch)
    group = main_mod.CatchAllExceptions(name="virl-test")
    monkeypatch.setattr(group, "main", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(main_mod.click, "secho", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_mod.traceback, "format_exc", lambda: "trace")
    monkeypatch.setattr("builtins.exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
    main_mod.virl.debug = True
    with pytest.raises(SystemExit):
        group()

    main_mod.virl.debug = False
    main_mod.virl.callback(debug=True)
    assert main_mod.virl.debug is True
