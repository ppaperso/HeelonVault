# Situation container (05/03/2026)

## Fait

- Mise en place d'un `Containerfile` multi-stage UBI9 (`builder` + `runtime`).
- Migration du conteneur vers Python `3.12`.
- Pinning explicite des images de base par digest (`BUILDER_BASE`, `RUNTIME_BASE`).
- Passage a une installation Python reproductible avec lockfile hashé:
  - fichier: `container/requirements-container.lock`
  - installation: `pip install --require-hashes -r requirements-container.lock`
- Ajout de labels OCI/metadonnees de conformité:
  - `org.opencontainers.image.revision`
  - `org.heelonys.security.policy`
  - `org.heelonys.sbom.provenance`
- Injection des metadonnees build via `container/build-and-sign.sh` (`--build-arg ...`).
- Build context durci avec `container/.containerignore` et usage explicite `--ignorefile`.
- Correctifs valides pendant la validation locale:
  - mismatch de hash corrige pour les wheels cibles Linux CPython 3.12
  - permission builder corrigee via `USER 0` dans le stage `builder`

## Validation effectuee

Commande de validation executee:

```bash
podman build --file container/Containerfile --ignorefile container/.containerignore --pull=always --tag heelonvault:phase2-validate .
```

Resultat actuel:

- Stage `builder`: OK (installation `--require-hashes` reussie).
- Stage `runtime`: ECHEC sur dependance systeme:
  - `error: No package matches 'libadwaita'`

## Reste a faire

1. Corriger la dependance systeme runtime:
   - remplacer `libadwaita` par le(s) paquet(s) reellement disponibles sur UBI9,
   - ou basculer sur une base runtime qui fournit `libadwaita`.
2. Relancer le build local jusqu'au succes complet.
3. Verifier les labels OCI sur l'image finale (`podman inspect`).
4. Rejouer le script `container/build-and-sign.sh` (push + cosign + SBOM) apres validation build local.

## Notes importantes

- Ne pas modifier `CHANGELOG` pour ce lot.
- Le lockfile hashé est cible Linux x86_64 / CPython 3.12.
