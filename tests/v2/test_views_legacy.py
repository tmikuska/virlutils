import types

from virl.cli.views.cluster.cluster_views import cluster_list_table
from virl.cli.views.console.console_views import console_table
from virl.cli.views.generate.nso.sync_result import sync_table
from virl.cli.views.groups.group_views import group_list_table
from virl.cli.views.labs.lab_views import lab_list_table, print_labs
from virl.cli.views.node_defs.node_def_views import node_def_list_table
from virl.cli.views.nodes.node_views import node_list_table
from virl.cli.views.search.views import repo_table
from virl.cli.views.users.user_views import user_list_table


def _patch_global_tabulate_fallback(monkeypatch):
    calls = []

    def fake_tabulate(_table, _headers, tablefmt):
        calls.append(tablefmt)
        if tablefmt == "fancy_grid":
            raise UnicodeEncodeError("utf-8", "x", 0, 1, "boom")
        return "grid-output"

    monkeypatch.setattr("tabulate.tabulate", fake_tabulate)
    return calls


def test_cluster_console_sync_repo_user_group_views(monkeypatch):
    calls = _patch_global_tabulate_fallback(monkeypatch)
    for path in [
        "virl.cli.views.cluster.cluster_views.click.echo",
        "virl.cli.views.console.console_views.click.echo",
        "virl.cli.views.generate.nso.sync_result.click.echo",
        "virl.cli.views.search.views.click.echo",
        "virl.cli.views.users.user_views.click.echo",
        "virl.cli.views.groups.group_views.click.echo",
    ]:
        monkeypatch.setattr(path, lambda _msg: None)
    for path in [
        "virl.cli.views.console.console_views.click.secho",
        "virl.cli.views.generate.nso.sync_result.click.secho",
        "virl.cli.views.users.user_views.click.secho",
        "virl.cli.views.groups.group_views.click.secho",
    ]:
        monkeypatch.setattr(path, lambda *args, **kwargs: None)

    cluster_list_table(
        {
            "id1": {
                "hostname": "h1",
                "is_controller": True,
                "kvm_vmx_enabled": False,
                "enough_cpus": True,
                "refplat_images_available": True,
                "lld_connected": False,
                "valid": True,
            }
        }
    )
    console_table([{"node": "n1", "console": "/lab/node/0"}])
    sync_table({"tailf-ncs:output": {"sync-result": [{"device": "d1", "result": True}, {"device": "d2", "result": False}]}})
    repo_table([{"full_name": "org/repo", "stargazers_count": 5, "description": "desc"}])
    user_list_table(
        [{"id": "u1", "username": "alice", "admin": True, "fullname": "Alice User", "email": "a@b", "groups": ["g1"], "labs": ["l1"]}],
        verbose=True,
    )
    group_list_table(
        [
            {
                "id": "g1",
                "name": "group",
                "description": "desc",
                "members": ["alice"],
                "associations": [{"title": "lab1", "permissions": ["lab_view"]}],
            }
        ],
        verbose=True,
    )

    assert "fancy_grid" in calls and "grid" in calls


def test_labs_node_defs_and_nodes_views(monkeypatch):
    calls = _patch_global_tabulate_fallback(monkeypatch)
    monkeypatch.setattr("virl.cli.views.labs.lab_views.click.echo", lambda _msg: None)
    monkeypatch.setattr("virl.cli.views.node_defs.node_def_views.click.echo", lambda _msg: None)
    monkeypatch.setattr("virl.cli.views.nodes.node_views.click.echo", lambda _msg: None)
    monkeypatch.setattr("virl.cli.views.labs.lab_views.click.secho", lambda *args, **kwargs: None)
    monkeypatch.setattr("virl.cli.views.nodes.node_views.click.secho", lambda *args, **kwargs: None)

    lab = types.SimpleNamespace(
        id="lab1",
        title="Lab 1",
        description="description",
        owner="owner1",
        state=lambda: "QUEUED",
        statistics={"nodes": 1, "links": 0, "interfaces": 1},
    )
    lab2 = types.SimpleNamespace(
        id="lab2",
        title="Lab 2",
        description="description",
        owner="owner2",
        state=lambda: "STOPPED",
        statistics={"nodes": 1, "links": 0, "interfaces": 1},
    )
    lab_list_table([lab], {"owner1": "alice"}, cached_labs=[lab2])
    print_labs([lab], {"owner1": "alice"})

    node_def_list_table(
        [
            {
                "id": "n1",
                "ui": {"label": "Router"},
                "general": {"description": "desc"},
                "device": {"interfaces": {"physical": [1, 2]}},
                "sim": {"linux_native": {"ram": 2048, "cpus": 2, "boot_disk_size": 20}},
            },
            {
                "id": "n2",
                "ui": {},
                "general": {"description": "desc"},
                "device": {"interfaces": {"physical": []}},
                "sim": {},
            },
        ]
    )

    class _Iface:
        def __init__(self, v4=None, v6=None):
            self.discovered_ipv4 = v4 or []
            self.discovered_ipv6 = v6 or []

    class _Node:
        def __init__(self, node_id, label, node_def, state, active, booted, compute_id=None):
            self.id = node_id
            self.label = label
            self.node_definition = node_def
            self.state = state
            self._active = active
            self._booted = booted
            self.compute_id = compute_id
            self.lab = types.SimpleNamespace(
                auto_sync=False,
                sync_states_if_outdated=lambda: None,
                sync_l3_addresses_if_outdated=lambda: None,
                sync_topology_if_outdated=lambda: None,
            )

        def is_booted(self):
            return self._booted

        def is_active(self):
            return self._active

        def interfaces(self):
            return [_Iface(v4=["10.0.0.1"], v6=["2001:db8::1"])]

    class _NoComputeNode(_Node):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            delattr(self, "compute_id")

    class _MissingSyncNode(_Node):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            delattr(self.lab, "sync_topology_if_outdated")

    nodes = [
        _Node("n1", "r1", "iosv", "BOOTED", True, True, compute_id="c1"),
        _NoComputeNode("n2", "r2", "iosv", "STOPPED", False, False),
        _Node("n3", "r3", "external_connector", "STOPPED", False, False, compute_id="c1"),
        _MissingSyncNode("n4", "r4", "iosv", "DEFINED_ON_CORE", True, False, compute_id="c1"),
    ]
    node_list_table(nodes, computes={"c1": {"hostname": "compute1"}})
    node_list_table(nodes, computes={})

    assert "fancy_grid" in calls and "grid" in calls
