#!/usr/bin/env bash
# Regression-Guard Pre-Commit-Hook.
#
# Prüft die GESTAGTEN .py-Änderungen auf destruktiven Symbol-Verlust / Datei-Kollaps,
# BEVOR sie committet werden — schliesst die Lücke, durch die direkte Refactors am
# Workflow-internen Guard vorbei schlüpfen.
#
# Installation:
#   ln -sf ../../scripts/pre-commit-hook.sh .git/hooks/pre-commit
#   (oder: cp scripts/pre-commit-hook.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit)
#
# Umgehen (bewusst, z.B. autorisiertes Löschen):
#   git commit --no-verify
#
# Exit-Code 1 (🔴 Symbol-Verlust) blockt den Commit; 🟡/🔵/🟢 lassen ihn durch.

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root" || exit 0

if [ ! -f regression_guard.py ]; then
    exit 0  # Tool nicht vorhanden → nicht blockieren
fi

python3 regression_guard.py --staged
status=$?

if [ "$status" -ne 0 ]; then
    echo ""
    echo "🛑 Regression-Guard: unautorisierter top-level Symbol-Verlust in gestagten Dateien."
    echo "   Prüfe die 🔴-Funde oben. Wenn das Löschen beabsichtigt ist:"
    echo "       git commit --no-verify"
    exit 1
fi
exit 0
