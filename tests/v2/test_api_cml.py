import importlib
import sys

import pytest

from virl.api.cml import CachedLab


def test_cached_lab_raises_for_missing_file():
    with pytest.raises(FileNotFoundError):
        CachedLab("id1", "/definitely/missing/cache.yaml")


def test_cached_lab_username_property_from_valid_cache(tmp_path):
    cache_file = tmp_path / "lab.yaml"
    cache_file.write_text(
        """
lab:
  title: My Lab
  description: Desc
nodes:
  - interfaces:
      - i1
links: []
""".strip() + "\n",
        encoding="utf-8",
    )
    lab = CachedLab("id1", str(cache_file))
    assert lab.username == "N/A"


def test_cml_loader_fallback_without_cloader(monkeypatch):
    import yaml

    # Force the "except ImportError: Loader" import path in virl.api.cml.
    monkeypatch.delattr(yaml, "CLoader", raising=False)
    sys.modules.pop("virl.api.cml", None)
    cml_module = importlib.import_module("virl.api.cml")
    try:
        assert cml_module.Loader is yaml.Loader
    finally:
        sys.modules.pop("virl.api.cml", None)
        importlib.import_module("virl.api.cml")
