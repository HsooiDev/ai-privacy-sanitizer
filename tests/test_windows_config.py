"""Local Windows config migration and sync-client hardlink regressions."""
import json
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import sanitizer as engine


@pytest.fixture
def packaged_paths(tmp_path, monkeypatch):
    legacy_root = tmp_path / 'synced-exe'
    legacy_root.mkdir()
    local = tmp_path / 'Local' / 'Sanitizer' / 'config.json'
    monkeypatch.setattr(engine.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(engine.sys, 'platform', 'win32')
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path/'Local'))
    monkeypatch.setattr(engine, 'PROJECT_ROOT', legacy_root)
    monkeypatch.setattr(engine, 'DEFAULT_CONFIG_PATH', local)
    monkeypatch.setattr(engine, 'EXAMPLE_CONFIG_PATH', legacy_root/'unused-example.json')
    return legacy_root/'config.json', local


def write_legacy(path):
    data = {'language': 'zh', 'theme': 'dark', 'hotkeys': {
        'sanitize': 'alt+s', 'restore': 'ctrl+shift+r'},
        'custom_dictionary': {'COMPANY': ['Synthetic Company']},
        'allowlist': ['fictional.invalid'], 'disabled_rules': [], 'unknown_future_option': 42}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return data


def test_packaged_windows_default_uses_local_appdata(packaged_paths):
    legacy, local = packaged_paths
    assert engine.get_default_config_path() == local


def test_migration_preserves_all_values_and_legacy_file(packaged_paths):
    legacy, local = packaged_paths
    expected = write_legacy(legacy)
    before = legacy.read_bytes()
    active = engine.PrivacySanitizer()
    assert active.config_path == local
    assert json.loads(local.read_text(encoding='utf-8')) == expected
    assert legacy.read_bytes() == before
    assert active.hotkeys == expected['hotkeys']
    assert not os.path.samefile(legacy, local)
    assert local.stat().st_nlink == 1


def test_sync_link_on_old_config_cannot_break_local_settings(packaged_paths):
    legacy, local = packaged_paths
    expected = write_legacy(legacy)
    active = engine.PrivacySanitizer()
    os.link(legacy, legacy.with_name('upload-staging'))
    assert legacy.stat().st_nlink == 2
    for _ in range(3):
        active.set_language('en')
        active.set_theme('light')
        assert active.language == 'en' and active.theme == 'light'
        assert active.hotkeys == expected['hotkeys']
    assert json.loads(legacy.read_text()) == expected


def test_existing_local_config_wins_without_reading_linked_legacy(packaged_paths):
    legacy, local = packaged_paths
    write_legacy(legacy)
    os.link(legacy, legacy.with_name('upload-staging'))
    local.parent.mkdir(parents=True)
    local.write_text('{"language":"en","theme":"light"}')
    before = local.read_bytes()
    active = engine.PrivacySanitizer()
    assert active.language == 'en' and local.read_bytes() == before


def test_explicit_config_does_not_migrate(packaged_paths):
    legacy, local = packaged_paths
    write_legacy(legacy)
    active = engine.PrivacySanitizer(config_path=legacy)
    assert active.config_path == legacy and not local.exists()


@pytest.mark.parametrize('invalid', ['[]', '{invalid'])
def test_bad_legacy_is_not_replaced_with_defaults(packaged_paths, invalid):
    legacy, local = packaged_paths
    legacy.write_text(invalid)
    with pytest.raises(ValueError):
        engine.PrivacySanitizer()
    assert legacy.read_text() == invalid and not local.exists()


def test_linked_legacy_and_local_configs_still_fail_closed(packaged_paths):
    legacy, local = packaged_paths
    write_legacy(legacy)
    alias = legacy.with_name('upload-staging')
    os.link(legacy, alias)
    with pytest.raises(OSError, match='unlinked'):
        engine.PrivacySanitizer()
    assert not local.exists()
    alias.unlink()
    active = engine.PrivacySanitizer()
    os.link(local, local.with_name('malicious-alias'))
    with pytest.raises(OSError, match='unlinked'):
        active.set_theme('light')


def test_failed_migration_retains_legacy_without_fallback(packaged_paths, monkeypatch):
    legacy, local = packaged_paths
    write_legacy(legacy)
    before = legacy.read_bytes()
    def deny(*args, **kwargs):
        raise PermissionError('synthetic')
    monkeypatch.setattr(engine, 'atomic_write_private', deny)
    with pytest.raises(PermissionError):
        engine.PrivacySanitizer()
    assert legacy.read_bytes() == before and not local.exists()


def test_concurrent_migration_does_not_overwrite_other_writer(packaged_paths, monkeypatch):
    legacy, local = packaged_paths
    write_legacy(legacy)
    atomic = engine.atomic_write_private
    def race(path, text, *, overwrite=True):
        assert not overwrite
        local.parent.mkdir(parents=True)
        local.write_text('{"language":"en"}')
        return atomic(path, text, overwrite=False)
    monkeypatch.setattr(engine, 'atomic_write_private', race)
    active = engine.PrivacySanitizer()
    assert active.language == 'en'
    assert json.loads(local.read_text()) == {'language': 'en'}


def test_gui_switches_and_all_pages_work_while_legacy_is_upload_linked(packaged_paths):
    import customtkinter as ctk
    from src.gui import _ModernControlCenter, _StableCTk
    legacy, local = packaged_paths
    expected = write_legacy(legacy)
    active = engine.PrivacySanitizer()
    os.link(legacy, legacy.with_name('upload-staging'))
    ctk.set_appearance_mode('Dark')
    root = _StableCTk()
    root.withdraw()
    try:
        win = _ModernControlCenter(root, active)
        for _ in range(2):
            win._toggle_theme()
            win._toggle_language()
            for page in ('sandbox', 'dict', 'vault', 'guide', 'home'):
                win._on_nav_selected(win._nav_key_to_label[page])
                assert win._active_page_key == page
            assert active.hotkeys == expected['hotkeys']
        assert active.config_path == local and local.stat().st_nlink == 1
        assert legacy.stat().st_nlink == 2
    finally:
        for timer in root.tk.splitlist(root.tk.call('after', 'info')):
            root.tk.call('after', 'cancel', timer)
        root.destroy()
