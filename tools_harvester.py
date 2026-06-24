# -*- coding: utf-8 -*-
"""
tools_harvester.py - Collector fuer Tool-Dokumentationen (GCC, Clang, pytest, etc.)
===================================================================================

Sammelt offizielle Dokumentationen fuer Tools und speichert sie im Code-Vault.
Kann unabhängig von harvest.py aufgerufen werden.

Aufruf:
  python3 tools_harvester.py

Resumable: bereits gesammelte IDs werden uebersprungen.
"""

import os
import sys
import json
import time
import random
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))

from vibelike.framework.quelibrium.core.vault import Vault
from vibelike.framework.quelibrium.core.paths import CODE_VAULT_FILE, CODE_CACHE_FILE

# User-Agent für HTTP-Requests (erforderlich für Wikipedia)
USER_AGENT = (
    "VibelikeToolsHarvester/1.0 "
    "(vibelike; jakobnotter89@googlemail.com)"
)

# Tool-Dokumentations-URLs (offizielle Docs)
TOOL_DOCS = [
    # Compiler
    {
        "id": "GCC_DOCS",
        "urls": [
            "https://gcc.gnu.org/onlinedocs/gcc-13.2.0/gcc/",
            "https://gcc.gnu.org/onlinedocs/gcc-13.2.0/gccint/",
            "https://gcc.gnu.org/onlinedocs/libstdc++/latest/",
        ],
        "sector": "COMPILERS",
        "source": "GCC_OFFICIAL",
    },
    {
        "id": "CLANG_DOCS",
        "urls": [
            "https://clang.llvm.org/docs/",
            "https://clang.llvm.org/docs/CommandGuide/clang.html",
            "https://clang.llvm.org/docs/LanguageExtensions.html",
        ],
        "sector": "COMPILERS",
        "source": "CLANG_OFFICIAL",
    },
    {
        "id": "RUST_DOCS",
        "urls": [
            "https://doc.rust-lang.org/std/index.html",
            "https://doc.rust-lang.org/book/",
            "https://doc.rust-lang.org/rust-by-example/",
            "https://doc.rust-lang.org/nomicon/",
        ],
        "sector": "COMPILERS",
        "source": "RUST_OFFICIAL",
    },
    {
        "id": "GO_DOCS",
        "urls": [
            "https://pkg.go.dev/std",
            "https://go.dev/doc/",
            "https://go.dev/doc/effective_go",
        ],
        "sector": "COMPILERS",
        "source": "GO_OFFICIAL",
    },
    {
        "id": "PYTHON_DOCS",
        "urls": [
            "https://docs.python.org/3/library/functions.html",
            "https://docs.python.org/3/reference/datamodel.html",
            "https://docs.python.org/3/c-api/index.html",
            "https://docs.python.org/3/extending/index.html",
        ],
        "sector": "COMPILERS",
        "source": "PYTHON_OFFICIAL",
    },
    # Build Systems
    {
        "id": "CMAKE_DOCS",
        "urls": [
            "https://cmake.org/cmake/help/latest/",
            "https://cmake.org/cmake/help/latest/guide/tutorial/index.html",
        ],
        "sector": "BUILD_SYSTEMS",
        "source": "CMAKE_OFFICIAL",
    },
    {
        "id": "MESON_DOCS",
        "urls": [
            "https://mesonbuild.com/Quick-guide.html",
            "https://mesonbuild.com/Reference-manual.html",
        ],
        "sector": "BUILD_SYSTEMS",
        "source": "MESON_OFFICIAL",
    },
    {
        "id": "BAZEL_DOCS",
        "urls": [
            "https://bazel.build/start",
            "https://bazel.build/rules/lib/rules/",
        ],
        "sector": "BUILD_SYSTEMS",
        "source": "BAZEL_OFFICIAL",
    },
    {
        "id": "MAKE_DOCS",
        "urls": [
            "https://www.gnu.org/software/make/manual/",
            "https://www.gnu.org/software/make/manual/make.html",
        ],
        "sector": "BUILD_SYSTEMS",
        "source": "MAKE_OFFICIAL",
    },
    # Test Runner
    {
        "id": "PYTEST_DOCS",
        "urls": [
            "https://docs.pytest.org/en/stable/",
            "https://docs.pytest.org/en/stable/how-to/usage.html",
            "https://docs.pytest.org/en/stable/how-to/fixtures.html",
        ],
        "sector": "TEST_RUNNERS",
        "source": "PYTEST_OFFICIAL",
    },
    {
        "id": "JUNIT_DOCS",
        "urls": [
            "https://junit.org/junit5/docs/current/user-guide/",
            "https://junit.org/junit5/docs/current/api/",
        ],
        "sector": "TEST_RUNNERS",
        "source": "JUNIT_OFFICIAL",
    },
    {
        "id": "GOOGLE_TEST_DOCS",
        "urls": [
            "https://google.github.io/googletest/",
            "https://google.github.io/googletest/primer.html",
        ],
        "sector": "TEST_RUNNERS",
        "source": "GOOGLE_TEST_OFFICIAL",
    },
    {
        "id": "CTEST_DOCS",
        "urls": [
            "https://cmake.org/cmake/help/latest/manual/ctest.1.html",
        ],
        "sector": "TEST_RUNNERS",
        "source": "CTEST_OFFICIAL",
    },
    # Git
    {
        "id": "GIT_DOCS",
        "urls": [
            "https://git-scm.com/doc",
            "https://git-scm.com/docs/user-manual.html",
            "https://git-scm.com/docs/git-glossary.html",
        ],
        "sector": "VERSION_CONTROL",
        "source": "GIT_OFFICIAL",
    },
    {
        "id": "GITHUB_DOCS",
        "urls": [
            "https://docs.github.com/en",
            "https://docs.github.com/en/actions",
        ],
        "sector": "VERSION_CONTROL",
        "source": "GITHUB_OFFICIAL",
    },
    # Debugging
    {
        "id": "GDB_DOCS",
        "urls": [
            "https://sourceware.org/gdb/current/onlinedocs/gdb/",
        ],
        "sector": "DEBUGGING",
        "source": "GDB_OFFICIAL",
    },
    {
        "id": "VALGRIND_DOCS",
        "urls": [
            "https://valgrind.org/docs/manual/manual.html",
        ],
        "sector": "DEBUGGING",
        "source": "VALGRIND_OFFICIAL",
    },
    {
        "id": "LLDB_DOCS",
        "urls": [
            "https://lldb.llvm.org/",
        ],
        "sector": "DEBUGGING",
        "source": "LLDB_OFFICIAL",
    },
    # Networking
    {
        "id": "CURL_DOCS",
        "urls": [
            "https://curl.se/docs/",
            "https://curl.se/docs/manpage.html",
        ],
        "sector": "NETWORKING",
        "source": "CURL_OFFICIAL",
    },
    {
        "id": "OPENSSL_DOCS",
        "urls": [
            "https://www.openssl.org/docs/",
            "https://www.openssl.org/docs/manmaster/man1/",
        ],
        "sector": "SECURITY",
        "source": "OPENSSL_OFFICIAL",
    },
    {
        "id": "NCURSES_DOCS",
        "urls": [
            "https://www.gnu.org/software/ncurses/ncurses.html",
        ],
        "sector": "TERMINAL",
        "source": "NCURSES_OFFICIAL",
    },
    # Containers
    {
        "id": "DOCKER_DOCS",
        "urls": [
            "https://docs.docker.com/",
            "https://docs.docker.com/reference/",
            "https://docs.docker.com/engine/reference/commandline/cli/",
        ],
        "sector": "CONTAINERS",
        "source": "DOCKER_OFFICIAL",
    },
    {
        "id": "PODMAN_DOCS",
        "urls": [
            "https://docs.podman.io/en/",
        ],
        "sector": "CONTAINERS",
        "source": "PODMAN_OFFICIAL",
    },
    {
        "id": "KUBERNETES_DOCS",
        "urls": [
            "https://kubernetes.io/docs/home/",
            "https://kubernetes.io/docs/reference/",
        ],
        "sector": "CONTAINERS",
        "source": "KUBERNETES_OFFICIAL",
    },
    # Shells
    {
        "id": "BASH_DOCS",
        "urls": [
            "https://www.gnu.org/software/bash/manual/",
            "https://www.gnu.org/software/bash/manual/bash.html",
        ],
        "sector": "SHELLS",
        "source": "BASH_OFFICIAL",
    },
    {
        "id": "ZSH_DOCS",
        "urls": [
            "https://zsh.sourceforge.io/Doc/",
            "https://zsh.sourceforge.io/Guide/zshguide.html",
        ],
        "sector": "SHELLS",
        "source": "ZSH_OFFICIAL",
    },
    # Package Managers
    {
        "id": "APT_DOCS",
        "urls": [
            "https://wiki.debian.org/Apt",
            "https://manpages.debian.org/apt.8",
        ],
        "sector": "PACKAGE_MANAGERS",
        "source": "APT_OFFICIAL",
    },
    {
        "id": "PIP_DOCS",
        "urls": [
            "https://pip.pypa.io/en/stable/",
            "https://pip.pypa.io/en/stable/cli/",
        ],
        "sector": "PACKAGE_MANAGERS",
        "source": "PIP_OFFICIAL",
    },
    {
        "id": "NPM_DOCS",
        "urls": [
            "https://docs.npmjs.com/",
            "https://docs.npmjs.com/cli/",
        ],
        "sector": "PACKAGE_MANAGERS",
        "source": "NPM_OFFICIAL",
    },
    # Text Processing
    {
        "id": "SED_DOCS",
        "urls": [
            "https://www.gnu.org/software/sed/manual/",
        ],
        "sector": "TEXT_PROCESSING",
        "source": "SED_OFFICIAL",
    },
    {
        "id": "AWK_DOCS",
        "urls": [
            "https://www.gnu.org/software/gawk/manual/",
        ],
        "sector": "TEXT_PROCESSING",
        "source": "AWK_OFFICIAL",
    },
    {
        "id": "GREP_DOCS",
        "urls": [
            "https://www.gnu.org/software/grep/manual/",
        ],
        "sector": "TEXT_PROCESSING",
        "source": "GREP_OFFICIAL",
    },
    {
        "id": "JQ_DOCS",
        "urls": [
            "https://stedolan.github.io/jq/manual/",
        ],
        "sector": "TEXT_PROCESSING",
        "source": "JQ_OFFICIAL",
    },
    {
        "id": "FZF_DOCS",
        "urls": [
            "https://github.com/junegunn/fzf",
        ],
        "sector": "TEXT_PROCESSING",
        "source": "FZF_OFFICIAL",
    },
    # System Tools
    {
        "id": "COREUTILS_DOCS",
        "urls": [
            "https://www.gnu.org/software/coreutils/manual/",
        ],
        "sector": "SYSTEM_TOOLS",
        "source": "COREUTILS_OFFICIAL",
    },
    {
        "id": "FINDUTILS_DOCS",
        "urls": [
            "https://www.gnu.org/software/findutils/manual/",
        ],
        "sector": "SYSTEM_TOOLS",
        "source": "FINDUTILS_OFFICIAL",
    },
]


class CodeVaultWriter:
    """Atomic-append-Wrapper um Vault + Embedding-Cache."""

    EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self, device="cuda"):
        from sentence_transformers import SentenceTransformer
        print(f"[tools-harvester] Loading model: {self.EMBEDDING_MODEL} (device={device})")
        self.model = SentenceTransformer(self.EMBEDDING_MODEL, device=device)

        self.vault = Vault(CODE_VAULT_FILE)
        try:
            self.archive = self.vault.load() or []
        except Exception:
            self.archive = []
        print(f"[tools-harvester] Existing docs: {len(self.archive)}")

        # Embedding-Cache
        if os.path.exists(CODE_CACHE_FILE):
            try:
                with open(CODE_CACHE_FILE, "rb") as f:
                    self.cache = pickle.load(f)
            except Exception:
                self.cache = {}
        else:
            self.cache = {}
        print(f"[tools-harvester] Existing embeddings: {len(self.cache)}")

        self.existing_ids = set(str(d.get("id", "")) for d in self.archive)
        self._buffer = []

    def has(self, doc_id):
        return str(doc_id) in self.existing_ids

    def add(self, doc):
        """Buffer einen neuen Doc. flush() schreibt auf Disk."""
        doc_id = str(doc.get("id", ""))
        if not doc_id or doc_id in self.existing_ids:
            return False
        self._buffer.append(doc)
        self.existing_ids.add(doc_id)
        return True

    def flush(self, batch_size=64):
        if not self._buffer:
            return 0
        # Embed in Batches
        texts = []
        for d in self._buffer:
            t = d.get("content") or d.get("text") or ""
            if not isinstance(t, str):
                t = str(t)
            texts.append(t[:512] if t else "(empty)")

        import numpy as np
        embs = self.model.encode(
            texts, batch_size=batch_size,
            convert_to_numpy=True, show_progress_bar=False
        )
        for d, e in zip(self._buffer, embs):
            self.cache[str(d.get("id"))] = e.astype("float32")
            self.archive.append(d)

        n = len(self._buffer)
        self._buffer.clear()

        # Auf Disk
        self.vault.save(self.archive)
        import pickle
        tmp = CODE_CACHE_FILE + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump(self.cache, f, protocol=4)
        os.replace(tmp, CODE_CACHE_FILE)
        return n


def _fetch_url(url):
    """Holt Text von einer URL."""
    import re as _re
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Entferne Scripts, Styles
        html = _re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=_re.DOTALL | _re.IGNORECASE)
        html = _re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=_re.DOTALL | _re.IGNORECASE)

        # Hauptinhalt extrahieren
        main_match = _re.search(r"<main[^>]*>(.*?)</main>", html, flags=_re.DOTALL | _re.IGNORECASE)
        if main_match:
            html = main_match.group(1)
        else:
            article_match = _re.search(r"<article[^>]*>(.*?)</article>", html, flags=_re.DOTALL | _re.IGNORECASE)
            if article_match:
                html = article_match.group(1)

        # HTML-Tags entfernen
        text = _re.sub(r"<[^>]+>", " ", html)
        # HTML-Entities
        text = (text.replace("&nbsp;", " ")
                    .replace("&amp;", "&")
                    .replace("&lt;", "<")
                    .replace("&gt;", ">")
                    .replace("&quot;", '"'))
        # Whitespace normalisieren
        text = _re.sub(r"\s+", " ", text).strip()
        return text
    except Exception as e:
        print(f"    URL {url} Fehler: {e}")
        return None


def harvest_tool_docs():
    """Sammelt offizielle Dokumentationen für Tools."""
    import pickle
    import random

    writer = CodeVaultWriter(device="cuda")
    added = 0
    skipped = 0
    failed = 0

    print(f"\n[tools] {len(TOOL_DOCS)} Tool-Dokumentationen")

    for doc_config in TOOL_DOCS:
        base_id = doc_config["id"]
        urls = doc_config["urls"]
        sector = doc_config["sector"]
        source = doc_config["source"]

        for i, url in enumerate(urls):
            doc_id = f"{base_id}-{i}"
            if writer.has(doc_id):
                skipped += 1
                continue

            text = _fetch_url(url)
            if not text or len(text) < 500:
                failed += 1
                continue

            # Titel aus URL extrahieren
            title = url.split("/")[-1].replace(".html", "").replace("-", " ")
            if not title or title == "index":
                title = f"{source}: Documentation {i+1}"

            writer.add({
                "id": doc_id,
                "content": text[:8000],
                "title": f"{source}: {title}".strip(": "),
                "source": source,
                "sector": sector,
                "url": url,
                "lang": "en",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            added += 1

            if added % 8 == 0:
                n = writer.flush()
                print(f"  +{added}, saved {n}")

            time.sleep(1.0 + random.uniform(0, 0.5))

    n = writer.flush()
    print(f"[tools] done: +{added}, {skipped} skipped, {failed} failed")
    return added


if __name__ == "__main__":
    start = time.time()
    total_added = harvest_tool_docs()
    elapsed = (time.time() - start) / 60
    print(f"\n=== Done: +{total_added} new tool docs in {elapsed:.1f} min ===")
    print(f"    Total Code-Vault: {len(writer.archive)} docs, {len(writer.cache)} embeddings")
