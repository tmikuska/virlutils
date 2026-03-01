from virl.generators.ansible_inventory import ansible_inventory_generator, generate_inventory_dict, render_inventory


class FakeInterface:
    def __init__(self, ipv4=None, ipv6=None):
        self.discovered_ipv4 = ipv4 or []
        self.discovered_ipv6 = ipv6 or []


class FakeNode:
    def __init__(self, label, node_id, definition, tags=None, interfaces=None):
        self.label = label
        self.id = node_id
        self.node_definition = definition
        self._tags = tags or []
        self._interfaces = interfaces or []

    def tags(self):
        return self._tags

    def interfaces(self):
        return self._interfaces


class FakeLab:
    def __init__(self, lab_id, title, nodes):
        self.id = lab_id
        self.title = title
        self._nodes = nodes

    def nodes(self):
        return self._nodes


class FakeServer:
    host = "example.local"
    user = "cml-user"


class _RaisingNodeType:
    def lower(self):
        raise KeyError("bad node type")


def test_generate_inventory_places_tagged_nodes_into_children_group():
    node = FakeNode(
        label="rtr-1",
        node_id="node1",
        definition="iosv",
        tags=["ansible_group=routers"],
        interfaces=[FakeInterface(ipv4=["10.0.0.1"])],
    )
    lab = FakeLab("lab-id", "Demo Lab", [node])

    inventory = generate_inventory_dict(lab, FakeServer)

    assert "routers" in inventory["all"]["children"]
    assert "rtr-1" in inventory["all"]["children"]["routers"]
    entry = inventory["all"]["children"]["routers"]["rtr-1"]
    assert entry["ansible_host"] == "10.0.0.1"
    assert entry["device_type"] == "ios"


def test_generate_inventory_uses_unknown_device_type_when_not_mapped():
    node = FakeNode(
        label="custom-1",
        node_id="node1",
        definition="custom-os",
        interfaces=[FakeInterface(ipv4=["10.0.0.5"])],
    )
    lab = FakeLab("lab-id", "Demo Lab", [node])

    inventory = generate_inventory_dict(lab, FakeServer)

    assert inventory["all"]["hosts"]["custom-1"]["device_type"] == "unknown"


def test_generate_inventory_maps_multiple_platform_types():
    nodes = [
        FakeNode("nx-1", "n1", "nxosv", interfaces=[FakeInterface(ipv4=["10.0.1.1"])]),
        FakeNode("xr-1", "n2", "xrv9k", interfaces=[FakeInterface(ipv4=["10.0.1.2"])]),
        FakeNode("asa-1", "n3", "asav", interfaces=[FakeInterface(ipv4=["10.0.1.3"])]),
        FakeNode("csr-1", "n4", "csr1000v", interfaces=[FakeInterface(ipv4=["10.0.1.4"])]),
    ]
    lab = FakeLab("lab-id", "Demo Lab", nodes)

    inventory = generate_inventory_dict(lab, FakeServer)

    assert inventory["all"]["hosts"]["nx-1"]["device_type"] == "nxos"
    assert inventory["all"]["hosts"]["xr-1"]["device_type"] == "iosxr"
    assert inventory["all"]["hosts"]["asa-1"]["device_type"] == "asa"
    assert inventory["all"]["hosts"]["csr-1"]["device_type"] == "ios"


def test_generate_inventory_handles_missing_node_definition():
    node = FakeNode("unknown-1", "node1", _RaisingNodeType(), interfaces=[FakeInterface(ipv4=["10.0.0.6"])])
    lab = FakeLab("lab-id", "Demo Lab", [node])

    inventory = generate_inventory_dict(lab, FakeServer)

    assert inventory["all"]["hosts"]["unknown-1"]["device_type"] == "unknown"


def test_generate_inventory_handles_existing_group_and_duplicate_host_name():
    nodes = [
        FakeNode(
            "rtr-1",
            "n1",
            "iosv",
            tags=["note=skip", "ansible_group=routers"],
            interfaces=[FakeInterface(ipv4=["10.0.0.1"])],
        ),
        FakeNode(
            "rtr-1",
            "n2",
            "iosv",
            tags=["ansible_group=routers"],
            interfaces=[FakeInterface(ipv4=["10.0.0.2"])],
        ),
    ]
    lab = FakeLab("lab-id", "Demo Lab", nodes)

    inventory = generate_inventory_dict(lab, FakeServer)

    # duplicate host name should not overwrite existing entry
    assert len(inventory["all"]["children"]["routers"]) == 1
    assert inventory["all"]["children"]["routers"]["rtr-1"]["ansible_host"] == "10.0.0.1"


def test_render_inventory_returns_none_for_unsupported_style():
    node = FakeNode(
        label="rtr-1",
        node_id="node1",
        definition="iosv",
        interfaces=[FakeInterface(ipv4=["10.0.0.1"])],
    )
    lab = FakeLab("lab-id", "Demo Lab", [node])

    assert render_inventory(lab, FakeServer, "json") is None


def test_ansible_inventory_generator_renders_ini_style():
    node = FakeNode(
        label="rtr-1",
        node_id="node1",
        definition="iosv",
        tags=["ansible_group=routers"],
        interfaces=[FakeInterface(ipv4=["10.0.0.1"])],
    )
    lab = FakeLab("lab-id", "Demo Lab", [node])

    rendered = ansible_inventory_generator(lab, FakeServer, style="ini")

    assert rendered is not None
    assert "[routers]" in rendered
    assert "rtr-1" in rendered
