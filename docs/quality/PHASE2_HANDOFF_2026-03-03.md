# Phase 2 Handoff (2026-03-03)

## État validé en fin de session

- Phase 1 terminée: `W1203` + `W0613` nettoyés.
- Score Pylint après Phase 1: `9.57/10 (previous run: 9.45/10, +0.12)`.
- Findings totaux: `202` (vs `258` avant Phase 1, delta `-56`).
- Objectif Phase 2: réduire `W0718` (exceptions trop larges) sans régression fonctionnelle.

## Priorités Phase 2 (ordre d'attaque)

1. `src/services/auth_service.py`
2. `src/services/backup_service.py`
3. `src/services/password_repository.py`
4. `src/services/totp_service.py`
5. `src/services/password_service.py`
6. `src/services/csv_importer.py`
7. `src/services/login_attempt_tracker.py`

## Règles de correction à appliquer

- Remplacer `except Exception:` par exceptions ciblées (`sqlite3.Error`, `ValueError`, `OSError`, `json.JSONDecodeError`, etc.) selon le contexte.
- Garder `logger.exception(...)` quand on remonte une erreur; sinon `logger.warning/error` avec contexte.
- Conserver le comportement utilisateur: pas de changement UX/fonctionnel non demandé.
- Éviter les `type: ignore` de confort.

## Commandes de reprise (demain)

```bash
# 1) Vérifier le baseline courant
/home/ppaadmin/Vscode/HeelonVault/venv-dev/bin/python -m pylint src > logs/pylint_report_phase2_work.txt 2>&1 || true

# 2) Lister uniquement W0718
grep -E "^[^:]+:[0-9]+:[0-9]+: W0718:" logs/pylint_report_phase2_work.txt

# 3) Après corrections, relancer Pylint complet
/home/ppaadmin/Vscode/HeelonVault/venv-dev/bin/python -m pylint src > logs/pylint_report_phase2.txt 2>&1 || true

# 4) Vérifier score + compte W0718
grep -E "Your code has been rated at" logs/pylint_report_phase2.txt
grep -E "^[^:]+:[0-9]+:[0-9]+: W0718:" logs/pylint_report_phase2.txt | wc -l
```

## Contrôles stabilité minimum

```bash
# Compilation syntaxique globale
/home/ppaadmin/Vscode/HeelonVault/venv-dev/bin/python -m py_compile $(find src -name "*.py")
```

## Notes importantes

- Le flux “changement mot de passe maître + réchiffrement du coffre” est déjà intégré dans `src/app/application.py`.
- Le dialogue centralisé de compte est ajouté: `src/ui/dialogs/manage_account_dialog.py`.
- Les rapports lint complets de référence sont présents dans `logs/pylint_report_full.txt` et `logs/pylint_report_phase1.txt`.

## Mini checklist (démarrage demain) — 5 commandes

```bash
# 1) Se placer dans le repo
cd /home/ppaadmin/Vscode/HeelonVault

# 2) Vérifier que la branche locale est bien à jour
git pull --ff-only origin main

# 3) Générer un état de travail Pylint pour Phase 2
/home/ppaadmin/Vscode/HeelonVault/venv-dev/bin/python -m pylint src > logs/pylint_report_phase2_work.txt 2>&1 || true

# 4) Lister uniquement les W0718 à traiter
grep -E "^[^:]+:[0-9]+:[0-9]+: W0718:" logs/pylint_report_phase2_work.txt

# 5) Après corrections, contrôle final rapide (score + syntaxe)
grep -E "Your code has been rated at" logs/pylint_report_phase2_work.txt | tail -n 1 && /home/ppaadmin/Vscode/HeelonVault/venv-dev/bin/python -m py_compile $(find src -name "*.py")
```
