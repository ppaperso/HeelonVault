# Plan Add/Update/Trash Secret (Rust)

## Scope

- Implémentation 100% Rust/GTK4.
- Le code Python legacy sert uniquement de référence fonctionnelle.
- Aucune modification du code Python.

## Objectifs Produit

- Réutiliser le formulaire existant (`AddEditDialog`) pour la création et la modification.
- Ajouter les actions rapides par icône dans la liste principale:
`crayon` pour modifier, `poubelle` pour déplacer en corbeille.
- Ajouter une corbeille complète:
liste, restauration, suppression définitive, vider la corbeille.

## Contraintes Techniques

- Schéma SQL Rust existant:
table `secret_items`, champ `title`, champ `deleted_at`.
- Sécurité multi-vault:
opérations de corbeille scoppées par `vault_id`.
- UX simple:
édition inline dans le panneau principal, sans dialogue modal pour le flux principal.

## Implémentation Réalisée

### 1) Repository (`secret_repository.rs`)

- Ajout des méthodes:
`list_trash_by_vault_id`, `update_secret_metadata`, `restore_secret`,
`permanent_delete`, `empty_trash`.
- SQL aligné sur le schéma réel `secret_items`.
- Garde-fous sur `deleted_at IS NULL/IS NOT NULL`.
- Scope `vault_id` appliqué sur restore/permanent delete/empty trash.

### 2) Service (`secret_service.rs`)

- Ajout de l’API:
`update_secret`, `list_trash_by_vault`, `restore_secret`,
`permanent_delete`, `empty_trash`.
- Règle clé implémentée:
en édition, `plaintext_secret = None` conserve le secret existant.
- Si un nouveau secret est fourni:
validation + chiffrement + mise à jour du blob.

### 3) Éditeur Create/Edit (`add_edit_dialog.rs`)

- Ajout du mode `DialogMode::{Create, Edit(Uuid)}`.
- Pré-remplissage des champs en mode `Edit` via `setup_for_edit`.
- Type verrouillé en édition pour éviter les transitions ambiguës de blob.
- Submit unifié:
création via `create_secret`, édition via `update_secret`.
- Évolution UX: intégration inline dans la vue principale via `secret_editor_view`.

### 4) Liste Principale (`main_window.rs`)

- Ajout d’un `secret_id` dans le view-model de ligne.
- Ajout de l’icône crayon:
ouvre l’éditeur inline en mode édition.
- Ajout de l’icône poubelle:
appelle `soft_delete` puis rafraîchit la liste active.
- Ajout d’un bouton d’accès à la corbeille dans le header.

### 5) Corbeille UI (`trash_dialog.rs`)

- Nouveau dialog Rust dédié.
- Liste des secrets supprimés du vault courant.
- Actions par ligne:
`Restaurer` et `Supprimer définitivement`.
- Action globale:
`Vider la corbeille` avec confirmation.
- Rafraîchissement de la liste principale après changement.

## Validation

- `cargo check` passe.
- validation manuelle UI confirmée sur les flux inline création / édition / retour.
- Tests repository ciblés:
update metadata, soft delete, restore, permanent delete, empty trash.
- Tests service ciblés:
update sans nouveau secret, cycle complet corbeille.

## Reste à Faire (itération suivante)

- Brancher la couche i18n Rust sur les nouvelles chaînes UI de corbeille/édition.
- Ajouter/mettre à jour les entrées `locales/messages.pot` + fichiers `.po`.
- Ajouter tests UI automatisés si souhaité (actuellement validation backend robuste + vérification manuelle UI recommandée).
