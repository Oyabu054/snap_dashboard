# -*- coding: utf-8 -*-
"""config.pyのBASE_DIR解決ロジックのテスト。

PyInstallerでexe化すると__file__はexe内部の一時展開フォルダを指してしまうため、
sys.frozen=Trueのときはsys.executableのフォルダをBASE_DIRとして使う必要がある。
通常実行時と挙動が分岐する箇所なので、両パターンをモックで検証する。
"""
import importlib
import sys
from pathlib import Path

import config


def test_base_dir_is_module_folder_when_not_frozen():
    assert config.BASE_DIR == Path(__file__).parent


def test_base_dir_is_executable_folder_when_frozen(tmp_path, monkeypatch):
    (tmp_path / "config.txt").write_text("[pi]\n", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "SnapMonitor.exe"))

    importlib.reload(config)
    try:
        assert config.BASE_DIR == tmp_path
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_resolve_path_keeps_absolute_path_unchanged():
    absolute = str(config.BASE_DIR / "somewhere" / "file.json")
    assert config._resolve_path(absolute) == absolute


def test_resolve_path_makes_relative_path_based_on_base_dir():
    assert config._resolve_path("cache") == str(config.BASE_DIR / "cache")
