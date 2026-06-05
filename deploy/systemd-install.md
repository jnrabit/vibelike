# hótr̥ — systemd-Autostart (Daemon + Web) + Sicherheits-Checkliste

Zwei System-Units: `hotr-retrieval.service` (warmer Dual-Vault) und `hotr-web.service`
(Dashboard + PTY-Terminal). Der Web-Service startet via `Requires`/`Type=notify` erst,
wenn die Vaults geladen sind → nach Reboot kommt alles von selbst warm hoch, Handy-
Reconnects sind sofort instant.

## 0. Vorher anpassen
- **Tailnet-IP** in `hotr-web.service` (`ExecStart … --host …`): deine via `tailscale ip -4`.
- Pfade/User gehen von `jnrabit` + `/home/jnrabit/vibelike` aus — sonst in beiden Units ändern.
- **API-Key** muss als chmod-600 EnvFile liegen: `~/.vibeweb.env` mit einer Zeile
  `ANTHROPIC_API_KEY=sk-ant-…` (siehe `deploy/vibeweb-start.sh`-Header). Ohne ihn läuft
  alles außer Codegen-Workflows.

## 1. Installieren
```bash
sudo cp deploy/hotr-retrieval.service deploy/hotr-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hotr-retrieval.service   # lädt Vaults (~40s), dann READY
sudo systemctl enable --now hotr-web.service         # startet erst nach READY
```

## 2. Prüfen
```bash
systemctl status hotr-retrieval.service hotr-web.service
journalctl -u hotr-retrieval.service -b --no-pager | tail        # "[daemon] READY"
curl -s 127.0.0.1:8810/health                                    # {"ready":true,…}
systemd-analyze security hotr-web.service                        # Sandbox-Rating
# Echter Test: rebooten, dann am Handy verbinden → muss instant + warm sein.
```
Stoppen/Neustart: `sudo systemctl restart hotr-web.service` (Daemon bleibt warm,
solange `hotr-retrieval` läuft).

## 3. Ehrliches Rest-Risiko (bewusst notiert)
Beide Services laufen als **`jnrabit`** — das PTY-Terminal ist faktisch eine Remote-Shell
in *deiner* Nutzer-Sitzung. Die Sandbox (`ProtectSystem=strict`, `NoNewPrivileges`,
`ProtectHome=read-only`, Schreibpfad nur `vibelike` + `.cache`) verhindert Schreibzugriff
außerhalb des Projekts und Privileg-Eskalation, **aber** ein kompromittiertes Terminal
kann `jnrabit`s Home noch **lesen** (z. B. `~/.ssh`). Echte Isolation = dedizierter
Service-User mit eigenem Home **oder** das geplante separate Gateway-Gerät. Für tailnet-
only + non-root + Token-Gate ist das interim vertretbar — aber kein Freibrief.

## 4. Manuelle Sicherheits-Checkliste (#38 — nur du, Konsole/Browser)
- [ ] **kali entfernen**: totes Gerät (119 Tage offline) aus der Tailscale-Admin-Konsole
      löschen → https://login.tailscale.com/admin/machines
- [ ] **Tailscale-ACL**: Policy so eng wie möglich — nur `pixel-5` (+ ggf. Gateway) darf
      `monolith:8800` / den Terminal-Port erreichen.
- [ ] **Separater Anthropic-Key mit Spend-Cap** fürs Terminal (Console) — *nicht* dein
      Hauptkonto-Key, mit hartem Monats-Limit.
- [ ] **Alten Key rotieren**: der vorher in Shell/Umgebung exponierte Key gehört in der
      Anthropic-Console widerrufen.
