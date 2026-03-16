# Modification & Corbeille Rust Optimisé

TL;DR: on garde ton architecture (Repository -> Service -> UI), on fait l’édition dans AddEditDialog sans nouvelle page, on ajoute une corbeille complète, et on verrouille 3 points critiques: schéma réel (secret_items/title), sécurité multi-vault, i18n Rust sans sur-complexifier le build.

Ajustements clés par rapport à ton draft

secrets -> secret_items et label -> title pour coller au schéma Rust existant.
update_secret(id, label, secret) est trop limité: l’édition actuelle touche aussi metadata_json, tags, expires_at, secret_type; il faut un update complet avec secret: Option<_>.
empty_trash() doit être scoped au vault courant (empty_trash(vault_id)), sinon risque cross-vault.
restore/permanent_delete doivent aussi être scope avec vault_id et deleted_at IS NOT NULL.
gio::SimpleAction: très bon pour commandes globales (ouvrir corbeille, vider corbeille), pas obligatoire pour chaque bouton de ligne.
GtkAlertDialog: OK si version GTK dispo; prévoir fallback sur le pattern de confirmation déjà utilisé si besoin.
i18n: réutiliser locales racine oui, mais intégrer progressivement côté Rust (éviter d’imposer build.rs + compilation .mo dès le départ si runtime suffit).
Étapes

Aligner les contrats sur le schéma Rust actuel (secret_items, title, deleted_at).
Étendre SecretRepository avec: update_secret_fields, list_trash_by_vault, restore_secret, permanent_delete, empty_trash(vault_id).
Implémenter les requêtes SQL avec garde-fous deleted_at IS NULL/IS NOT NULL et vault_id.
Étendre SecretService avec la logique d’édition hybride:
secret=None -> met à jour les champs non-secrets uniquement.
secret=Some -> rechiffre et met à jour le blob.
Adapter AddEditDialog en mode Create | Edit { secret_id } avec setup_for_edit.
Au submit en édition: champ secret vide => None (conserver l’ancien), sinon nouveau secret.
Dans main_window.rs, enrichir les rows avec id et ajouter les icônes:
crayon -> ouvre AddEditDialog en mode edit.
poubelle -> soft_delete + refresh.
Créer TrashDialog Rust complet: liste, restaurer, suppression définitive, vider corbeille avec confirmation.
Ajouter l’accès corbeille dans l’UI principale sans surcharger (menu/toolbar).
Intégrer les nouvelles chaînes dans locales racine (FR/DE/IT + messages.pot) et brancher la couche i18n Rust.
Ajouter tests repository/service + vérifications UI manuelles.
Fichiers principaux

secret_repository.rs
secret_service.rs
add_edit_dialog.rs
main_window.rs
rust/src/ui/dialogs/trash_dialog.rs (nouveau)
main.rs (init i18n si centralisée)
build.rs (uniquement si packaging .mo requis)
messages.pot
heelonvault.po
heelonvault.po
heelonvault.po
Vérification

Édition avec secret vide conserve le blob chiffré.
Édition avec secret saisi remplace le blob.
Liste principale exclut toujours deleted_at IS NOT NULL.
Corbeille ne montre que le vault courant.
Restaurer réaffiche en liste principale.
Suppression définitive + vider corbeille: confirmation + irréversibilité.
Nouvelles chaînes i18n affichées selon langue active.
