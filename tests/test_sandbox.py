"""Tests für den SandboxManager.

Hinweis: Die alten Tests waren gegen eine abgeschaffte Docker-Image-API geschrieben
(create_sandbox(image=...), run(...)). Die aktuelle Impl ist req_id/tool_name-basiert
mit echten Namespace-/Mount-Operationen. Hier werden die unit-sicheren Pfade getestet
(Fehlerverhalten, get/destroy); die privilegierten Mount-Pfade sind als Integration
markiert (brauchen echtes Tool + Mount-Rechte).
"""

import pytest

from vibelike.sandbox.manager import SandboxManager


def test_sandbox_manager_fixture(sandbox_manager: SandboxManager):
    """Fixture lädt korrekt."""
    assert sandbox_manager is not None
    assert isinstance(sandbox_manager, SandboxManager)


def test_create_unresolvable_tool_raises(sandbox_manager: SandboxManager):
    """create() mit unauflösbarem Tool wirft ValueError (vor jedem Mount)."""
    with pytest.raises(ValueError):
        sandbox_manager.create(req_id="req-x", tool_name="nonexistent-tool-xyz")


def test_get_unknown_returns_none(sandbox_manager: SandboxManager):
    """get() für unbekannte req_id gibt None."""
    assert sandbox_manager.get("does-not-exist") is None


def test_destroy_unknown_is_noop(sandbox_manager: SandboxManager):
    """destroy() einer unbekannten Sandbox ist ein No-Op (kein Fehler)."""
    sandbox_manager.destroy("does-not-exist")  # darf nicht werfen


def test_active_sandboxes_starts_empty(sandbox_manager: SandboxManager):
    """Frischer Manager hat keine aktiven Sandboxen."""
    assert sandbox_manager.active_sandboxes == {}


@pytest.mark.skip(reason="Integration: braucht auflösbares Tool + Mount-Rechte "
                         "(Namespace-Sandbox), nicht im Unit-Env lauffähig.")
def test_real_sandbox_lifecycle(sandbox_manager: SandboxManager):
    """create → get → destroy mit echtem Tool (privilegiert)."""
    sb = sandbox_manager.create(req_id="req-1", tool_name="echo")
    assert sandbox_manager.get("req-1") is sb
    sandbox_manager.destroy("req-1")
    assert sandbox_manager.get("req-1") is None
