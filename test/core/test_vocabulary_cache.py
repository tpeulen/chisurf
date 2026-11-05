"""The parsed mmCIF vocabulary is cached once per machine, by content, safely under concurrency.

`chisurf.core.support.vocabulary.dictionary` was re-parsed (1.3 s, 10.8 s cProfiled) whenever its
pickle under `<settings>/cache` missed -- every fresh settings folder and every batch worker -- and
its key was the files' paths and mtimes. These pin the cache that replaced it: content-keyed, one
shared user folder, atomic writes.
"""

from __future__ import annotations

import os
import pickle
import threading
import time

import pytest

from chisurf.core.support import vocabulary


@pytest.fixture
def tiny(tmp_path, monkeypatch):
    """Two small dictionaries in place of the bundled set, and a private cache folder."""
    dics = tmp_path / "dics"
    dics.mkdir()
    paths = []
    for name, category in (("a.dic", "alpha"), ("b.dic", "beta")):
        path = dics / name
        path.write_text(
            f"data_{name[0]}\n"
            f"save_{category}\n"
            f"    _category.id                  {category}\n"
            f"    _category.description         'a category'\n"
            "    save_\n"
        )
        paths.append(path)
    monkeypatch.setattr(vocabulary, "_paths", lambda: list(paths))
    monkeypatch.setenv("CHISURF_CACHE_DIR", str(tmp_path / "cache"))
    vocabulary.dictionary.cache_clear()
    yield paths
    vocabulary.dictionary.cache_clear()


def _parses(monkeypatch):
    """Count real parses: the dictionary class's constructor with files."""
    from mmfdb.schema.pdbx_metadata import MmcifDictionary

    count = {"n": 0}
    original = MmcifDictionary.__init__

    def counting(self, *paths):
        if paths:
            count["n"] += 1
        original(self, *paths)

    monkeypatch.setattr(MmcifDictionary, "__init__", counting)
    return count


def test_the_key_is_the_content_not_the_path_or_mtime(tiny, tmp_path):
    key = vocabulary._key(tiny)
    os.utime(tiny[0], (1_000_000, 1_000_000))
    assert vocabulary._key(tiny) == key, "a touched file with the same bytes is the same parse"
    moved = tmp_path / "elsewhere"
    moved.mkdir()
    copies = []
    for path in tiny:
        copy = moved / path.name
        copy.write_bytes(path.read_bytes())
        copies.append(copy)
    assert vocabulary._key(copies) == key, "another checkout of the same dictionaries"
    tiny[1].write_text(tiny[1].read_text() + "# edited\n")
    assert vocabulary._key(tiny) != key


def test_a_fresh_settings_folder_reuses_the_shared_parse(tiny, tmp_path, monkeypatch):
    parses = _parses(monkeypatch)
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings_one"))
    first = vocabulary.dictionary()
    assert parses["n"] == 1 and first.get_category("alpha") is not None
    vocabulary.dictionary.cache_clear()
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings_two"))  # a batch worker
    second = vocabulary.dictionary()
    assert parses["n"] == 1, "the second process parsed again"
    assert second.get_category("beta") is not None
    cached = list((tmp_path / "cache").glob("vocabulary-*.pickle"))
    assert len(cached) == 1 and not list((tmp_path / "cache").glob("*.tmp"))


def test_an_edited_dictionary_is_parsed_again(tiny, monkeypatch):
    parses = _parses(monkeypatch)
    vocabulary.dictionary()
    vocabulary.dictionary.cache_clear()
    tiny[0].write_text(tiny[0].read_text().replace("alpha", "gamma"))
    assert vocabulary.dictionary().get_category("gamma") is not None
    assert parses["n"] == 2


def test_a_truncated_cache_is_parsed_and_replaced(tiny, monkeypatch):
    vocabulary.dictionary()
    cache = vocabulary._cache_file(vocabulary._key(tiny))
    cache.write_bytes(cache.read_bytes()[:40])
    vocabulary.dictionary.cache_clear()
    parses = _parses(monkeypatch)
    assert vocabulary.dictionary().get_category("alpha") is not None
    assert parses["n"] == 1
    with cache.open("rb") as stream:
        assert pickle.load(stream).get_category("alpha") is not None


def test_concurrent_writers_never_expose_a_partial_cache(tiny):
    from mmfdb.schema.pdbx_metadata import MmcifDictionary

    parsed = MmcifDictionary(*tiny)
    cache = vocabulary._cache_file(vocabulary._key(tiny))
    stop = threading.Event()
    bad = []

    def reader():
        while not stop.is_set():
            if cache.exists():
                got = vocabulary._load(cache, MmcifDictionary)
                if got is None:
                    bad.append("partial")

    def writer():
        for _ in range(25):
            vocabulary._store(cache, parsed)

    readers = [threading.Thread(target=reader) for _ in range(3)]
    writers = [threading.Thread(target=writer) for _ in range(6)]
    for t in readers + writers:
        t.start()
    for t in writers:
        t.join()
    stop.set()
    for t in readers:
        t.join()
    assert not bad
    assert vocabulary._load(cache, MmcifDictionary).get_category("alpha") is not None
    assert not list(cache.parent.glob("*.tmp")), "a writer left its temporary file behind"


def test_only_long_unused_caches_of_other_keys_are_removed(tiny):
    vocabulary.dictionary()
    folder = vocabulary.cache_dir()
    old = folder / "vocabulary-oldkey.pickle"
    recent = folder / "vocabulary-otherworktree.pickle"
    for path in (old, recent):
        path.write_bytes(b"x")
    month_ago = time.time() - (vocabulary.STALE_DAYS + 1) * 86400.0
    os.utime(old, (month_ago, month_ago))
    vocabulary._prune(vocabulary._cache_file(vocabulary._key(tiny)))
    assert not old.exists() and recent.exists()


def test_the_cache_folder_follows_the_platform(monkeypatch, tmp_path):
    monkeypatch.delenv("CHISURF_CACHE_DIR", raising=False)
    monkeypatch.setattr(vocabulary.sys, "platform", "linux")
    monkeypatch.setattr(vocabulary.os, "name", "posix")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert vocabulary.cache_dir() == tmp_path / "xdg" / "chisurf"
    monkeypatch.setenv("CHISURF_CACHE_DIR", str(tmp_path / "mine"))
    assert vocabulary.cache_dir() == tmp_path / "mine"
