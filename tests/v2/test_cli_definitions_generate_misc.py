import types

from click.testing import CliRunner

from virl.api import NoPluginError
from virl.cli.definitions.images.export import commands as img_export_mod
from virl.cli.definitions.images.iimport.definition import commands as img_import_def_mod
from virl.cli.definitions.images.iimport.image_file import commands as img_file_import_mod
from virl.cli.definitions.images.ls import commands as img_ls_mod
from virl.cli.definitions.images.export.commands import export as export_image_def
from virl.cli.definitions.images.iimport.definition.commands import definition as import_image_def
from virl.cli.definitions.images.iimport.image_file.commands import image_file
from virl.cli.definitions.images.ls.commands import ls as ls_image_defs
from virl.cli.definitions.nodes.export import commands as node_export_mod
from virl.cli.definitions.nodes.ls import commands as node_ls_mod
from virl.cli.definitions.nodes.nimport import commands as node_import_mod
from virl.cli.definitions.nodes.export.commands import export as export_node_def
from virl.cli.definitions.nodes.ls.commands import ls as ls_node_defs
from virl.cli.definitions.nodes.nimport.commands import nimport
from virl.cli.down.commands import down
from virl.cli.generate.ansible import commands as gen_ansible_mod
from virl.cli.generate.ansible.commands import ansible
from virl.cli.generate.nso import commands as gen_nso_mod
from virl.cli.generate.nso.commands import nso
from virl.cli.generate.pyats import commands as gen_pyats_mod
from virl.cli.generate.pyats.commands import pyats
from virl.cli.rm.commands import rm


class _Defs:
    def __init__(self):
        self.uploaded_image_def = None
        self.uploaded_image_file = None
        self.uploaded_node_def = None

    def image_definitions(self):
        return [
            {
                "name": "img1",
                "id": "img1",
                "node_definition_id": "nd1",
                "label": "Image1",
                "description": "desc",
                "ram": 1024,
                "cpus": 1,
                "boot_disk_size": 8,
            }
        ]

    def node_definitions(self):
        return [
            {
                "id": "n1",
                "ui": {"label": "Router"},
                "general": {"description": "desc"},
                "device": {"interfaces": {"physical": [1]}},
                "sim": {"linux_native": {"ram": 512, "cpus": 1}},
            }
        ]

    def download_image_definition(self, image):
        if image == "bad":
            raise RuntimeError("bad image")
        return f"image:{image}"

    def upload_image_definition(self, contents):
        if contents == "bad":
            raise RuntimeError("bad upload")
        self.uploaded_image_def = contents

    def upload_image_file(self, filename, rename):
        if filename.endswith(".bad"):
            raise RuntimeError("bad file")
        self.uploaded_image_file = (filename, rename)

    def download_node_definition(self, node):
        if node == "bad":
            raise RuntimeError("bad node")
        return f"node:{node}"

    def upload_node_definition(self, contents):
        if contents == "bad":
            raise RuntimeError("bad node upload")
        self.uploaded_node_def = contents


class _Client:
    def __init__(self):
        self.definitions = _Defs()


class _Lab:
    def __init__(self, lab_id="lab123", title="Lab One", state="DEFINED_ON_CORE", active=False):
        self.id = lab_id
        self.title = title
        self._state = state
        self._active = active
        self.stopped = False
        self.wiped = False
        self.removed = False

    def is_active(self):
        return self._active

    def state(self):
        return self._state

    def stop(self, wait=False):
        self.stopped = True
        self._active = False

    def wipe(self, wait=False):
        self.wiped = True
        self._state = "DEFINED_ON_CORE"

    def remove(self):
        self.removed = True


def _patch_server_client(monkeypatch, modules, client, server_obj=None):
    server_obj = object() if server_obj is None else server_obj
    for mod in modules:
        monkeypatch.setattr(mod, "VIRLServer", lambda _s=server_obj: _s)
        monkeypatch.setattr(mod, "get_cml_client", lambda _server, _c=client: _c)


def _patch_list_viewer(monkeypatch, module, rendered_store):
    monkeypatch.setattr(
        module,
        "ViewerPlugin",
        lambda **_kwargs: (_ for _ in ()).throw(NoPluginError("none")),
    )
    assert CliRunner().invoke(ls_image_defs if module is img_ls_mod else ls_node_defs, []).exit_code == 0

    class _Viewer:
        def visualize(self, **kwargs):
            rendered_store.append(kwargs)

    monkeypatch.setattr(module, "ViewerPlugin", lambda **_kwargs: _Viewer())


def test_image_definition_paths(monkeypatch, tmp_path):
    client = _Client()
    _patch_server_client(monkeypatch, [img_export_mod, img_import_def_mod, img_file_import_mod, img_ls_mod], client)

    out_file = tmp_path / "img.yaml"
    assert CliRunner().invoke(export_image_def, ["img1", "--filename", str(out_file)]).exit_code == 0
    assert out_file.read_text() == "image:img1"
    assert CliRunner().invoke(export_image_def, ["bad"]).exit_code == 1

    in_file = tmp_path / "in.yaml"
    in_file.write_text("good")
    assert CliRunner().invoke(import_image_def, ["--filename", str(in_file)]).exit_code == 0
    assert client.definitions.uploaded_image_def == "good"
    bad_in = tmp_path / "bad.yaml"
    bad_in.write_text("bad")
    assert CliRunner().invoke(import_image_def, ["--filename", str(bad_in)]).exit_code == 1
    assert CliRunner().invoke(import_image_def, ["--filename", str(tmp_path / "missing.yaml")]).exit_code == 1

    img_file = tmp_path / "disk.qcow2"
    img_file.write_text("x")
    assert CliRunner().invoke(image_file, ["--filename", str(img_file), "--rename", "new-name"]).exit_code == 0
    assert client.definitions.uploaded_image_file == (str(img_file), "new-name")
    bad_img = tmp_path / "disk.bad"
    bad_img.write_text("x")
    assert CliRunner().invoke(image_file, ["--filename", str(bad_img)]).exit_code == 1
    assert CliRunner().invoke(image_file, ["--filename", str(tmp_path / "missing.img")]).exit_code == 1

    # No plugin path with an explicit image filter.
    monkeypatch.setattr(
        img_ls_mod,
        "ViewerPlugin",
        lambda **_kwargs: (_ for _ in ()).throw(NoPluginError("none")),
    )
    assert CliRunner().invoke(ls_image_defs, ["--image", "img1"]).exit_code == 0

    rendered = []
    _patch_list_viewer(monkeypatch, img_ls_mod, rendered)
    # Plugin path for listing all images.
    assert CliRunner().invoke(ls_image_defs, []).exit_code == 0
    assert CliRunner().invoke(ls_image_defs, ["--image", "img1"]).exit_code == 0
    assert CliRunner().invoke(ls_image_defs, ["--image", "does-not-exist"]).exit_code == 0
    assert rendered and "image_defs" in rendered[0]


def test_node_definition_paths(monkeypatch, tmp_path):
    client = _Client()
    _patch_server_client(monkeypatch, [node_export_mod, node_import_mod, node_ls_mod], client)

    assert CliRunner().invoke(export_node_def, ["n1", "--filename", str(tmp_path / "node.yaml")]).exit_code == 0
    assert CliRunner().invoke(export_node_def, ["bad"]).exit_code == 1

    node_in = tmp_path / "node_in.yaml"
    node_in.write_text("nodegood")
    assert CliRunner().invoke(nimport, ["--filename", str(node_in)]).exit_code == 0
    node_bad = tmp_path / "node_bad.yaml"
    node_bad.write_text("bad")
    assert CliRunner().invoke(nimport, ["--filename", str(node_bad)]).exit_code == 1
    assert CliRunner().invoke(nimport, ["--filename", str(tmp_path / "missing-node.yaml")]).exit_code == 1

    # No plugin path with an explicit node filter.
    monkeypatch.setattr(
        node_ls_mod,
        "ViewerPlugin",
        lambda **_kwargs: (_ for _ in ()).throw(NoPluginError("none")),
    )
    assert CliRunner().invoke(ls_node_defs, ["--node", "n1"]).exit_code == 0

    rendered = []
    _patch_list_viewer(monkeypatch, node_ls_mod, rendered)
    # Plugin path for listing all node definitions.
    assert CliRunner().invoke(ls_node_defs, []).exit_code == 0
    assert CliRunner().invoke(ls_node_defs, ["--node", "n1"]).exit_code == 0
    assert CliRunner().invoke(ls_node_defs, ["--node", "missing"]).exit_code == 0
    assert rendered and "node_defs" in rendered[0]


def test_down_and_rm_command_paths(monkeypatch):
    client = _Client()
    lab = _Lab(active=True, state="BOOTED")

    monkeypatch.setattr("virl.cli.down.commands.VIRLServer", lambda: object())
    monkeypatch.setattr("virl.cli.down.commands.get_cml_client", lambda _s: client)
    monkeypatch.setattr("virl.cli.down.commands.safe_join_existing_lab", lambda _id, _c: lab)
    monkeypatch.setattr("virl.cli.down.commands.safe_join_existing_lab_by_title", lambda _n, _c: lab)
    monkeypatch.setattr("virl.cli.down.commands.get_current_lab", lambda: "lab123")
    assert CliRunner().invoke(down, ["--id", "lab123"]).exit_code == 0
    assert lab.stopped is True

    lab._active = False
    assert CliRunner().invoke(down, ["--lab-name", "Lab One"]).exit_code == 0
    monkeypatch.setattr("virl.cli.down.commands.safe_join_existing_lab", lambda _id, _c: None)
    monkeypatch.setattr("virl.cli.down.commands.safe_join_existing_lab_by_title", lambda _n, _c: None)
    monkeypatch.setattr("virl.cli.down.commands.get_current_lab", lambda: None)
    assert CliRunner().invoke(down, []).exit_code == 1

    lab2 = _Lab(active=True, state="BOOTED")
    monkeypatch.setattr("virl.cli.rm.commands.VIRLServer", lambda: object())
    monkeypatch.setattr("virl.cli.rm.commands.get_cml_client", lambda _s: client)
    monkeypatch.setattr("virl.cli.rm.commands.get_current_lab", lambda: "lab123")
    monkeypatch.setattr("virl.cli.rm.commands.safe_join_existing_lab", lambda _id, _c: lab2)
    monkeypatch.setattr("builtins.input", lambda _p: "y")
    monkeypatch.setattr("virl.cli.rm.commands.check_lab_cache", lambda _id: "/tmp/missing-cache")
    monkeypatch.setattr("virl.cli.rm.commands.os.remove", lambda _p: (_ for _ in ()).throw(OSError("missing")))
    monkeypatch.setattr("virl.cli.rm.commands.clear_current_lab", lambda *args, **kwargs: None)
    assert CliRunner().invoke(rm, ["--force", "--no-confirm", "--from-cache"]).exit_code == 0
    assert lab2.removed is True

    monkeypatch.setattr("virl.cli.rm.commands.safe_join_existing_lab", lambda _id, _c: None)
    assert CliRunner().invoke(rm, []).exit_code == 1
    monkeypatch.setattr("virl.cli.rm.commands.get_current_lab", lambda: None)
    assert CliRunner().invoke(rm, []).exit_code == 1


def test_generate_ansible_and_pyats_paths(monkeypatch, tmp_path):
    server = types.SimpleNamespace(host="h", user="u", passwd="p", config={})
    client = _Client()
    lab = _Lab(lab_id="lab123", title="Lab One")

    _patch_server_client(monkeypatch, [gen_ansible_mod, gen_pyats_mod], client, server_obj=server)
    monkeypatch.setattr(gen_ansible_mod, "get_current_lab", lambda: "lab123")
    monkeypatch.setattr(gen_ansible_mod, "safe_join_existing_lab", lambda _id, _c: lab)
    monkeypatch.setattr(gen_ansible_mod, "ansible_inventory_generator", lambda _lab, _server, style="yaml": "INV")
    out = tmp_path / "inv.ini"
    assert CliRunner().invoke(ansible, ["--style", "ini", "--output", str(out)]).exit_code == 0
    assert out.read_text() == "INV"
    monkeypatch.setattr(gen_ansible_mod, "ansible_inventory_generator", lambda *_a, **_k: None)
    assert CliRunner().invoke(ansible, []).exit_code == 1
    monkeypatch.setattr(gen_ansible_mod, "safe_join_existing_lab", lambda _id, _c: None)
    assert CliRunner().invoke(ansible, []).exit_code == 1
    monkeypatch.setattr(gen_ansible_mod, "get_current_lab", lambda: None)
    assert CliRunner().invoke(ansible, []).exit_code == 1

    monkeypatch.setattr(gen_pyats_mod, "get_current_lab", lambda: "lab123")
    monkeypatch.setattr(gen_pyats_mod, "safe_join_existing_lab", lambda _id, _c: lab)
    monkeypatch.setattr(gen_pyats_mod, "pyats_testbed_generator", lambda _lab: "TB")
    tbo = tmp_path / "tb.yaml"
    assert CliRunner().invoke(pyats, ["--output", str(tbo)]).exit_code == 0
    assert tbo.read_text() == "TB"
    monkeypatch.setattr(gen_pyats_mod, "pyats_testbed_generator", lambda _lab: None)
    assert CliRunner().invoke(pyats, []).exit_code == 1
    monkeypatch.setattr(gen_pyats_mod, "safe_join_existing_lab", lambda _id, _c: None)
    assert CliRunner().invoke(pyats, []).exit_code == 1
    monkeypatch.setattr(gen_pyats_mod, "get_current_lab", lambda: None)
    assert CliRunner().invoke(pyats, []).exit_code == 1


def test_generate_nso_paths(monkeypatch, tmp_path):
    server = types.SimpleNamespace(host="h", user="u", passwd="p", config={})
    client = _Client()
    lab = _Lab(lab_id="lab123", title="Lab One")

    _patch_server_client(monkeypatch, [gen_nso_mod], client, server_obj=server)
    monkeypatch.setattr(gen_nso_mod, "get_current_lab", lambda: "lab123")
    monkeypatch.setattr(gen_nso_mod, "safe_join_existing_lab", lambda _id, _c: lab)
    monkeypatch.setattr(gen_nso_mod, "nso_payload_generator", lambda _lab, _server: "<xml/>")

    class _NSO:
        def update_devices(self, _inv):
            return types.SimpleNamespace(ok=True, text="ok")

        def perform_sync_from(self):
            return types.SimpleNamespace(json=lambda: {"tailf-ncs:output": {"sync-result": []}})

    monkeypatch.setattr(gen_nso_mod, "NSO", _NSO)
    sync_called = []
    monkeypatch.setattr(gen_nso_mod, "sync_table", lambda payload: sync_called.append(payload))
    assert CliRunner().invoke(nso, ["--syncfrom"]).exit_code == 0
    assert sync_called

    out_xml = tmp_path / "payload.xml"
    assert CliRunner().invoke(nso, ["--output", str(out_xml)]).exit_code == 0
    assert out_xml.read_text() == "<xml/>"

    monkeypatch.setattr(gen_nso_mod, "nso_payload_generator", lambda _lab, _server: None)
    assert CliRunner().invoke(nso, []).exit_code == 1
    monkeypatch.setattr(gen_nso_mod, "nso_payload_generator", lambda _lab, _server: "<xml/>")

    class _BadNSO:
        def update_devices(self, _inv):
            return types.SimpleNamespace(ok=False, text="failed")

        def perform_sync_from(self):
            return types.SimpleNamespace(json=lambda: {})

    monkeypatch.setattr(gen_nso_mod, "NSO", _BadNSO)
    assert CliRunner().invoke(nso, []).exit_code == 0
    monkeypatch.setattr(gen_nso_mod, "safe_join_existing_lab", lambda _id, _c: None)
    assert CliRunner().invoke(nso, []).exit_code == 1
    monkeypatch.setattr(gen_nso_mod, "get_current_lab", lambda: None)
    assert CliRunner().invoke(nso, []).exit_code == 1
