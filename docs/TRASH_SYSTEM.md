# Système de corbeille

## Vue d'ensemble

Le gestionnaire de mots de passe dispose désormais d'un système de corbeille qui permet de récupérer des entrées supprimées accidentellement.

## Fonctionnalités

### Suppression douce (Soft Delete)

- Lorsque vous supprimez une entrée, elle n'est pas immédiatement supprimée de la base de données
- L'entrée est marquée avec une date de suppression (`deleted_at`)
- Les entrées supprimées n'apparaissent plus dans la liste principale

### Corbeille

- Accessible via le menu principal → "Corbeille"
- Liste toutes les entrées supprimées
- Affiche les informations de base : titre, nom d'utilisateur, URL, catégorie

### Restauration

- Chaque entrée dans la corbeille peut être restaurée individuellement
- La restauration retire la date de suppression et l'entrée réapparaît dans la liste principale

### Suppression définitive

- Une entrée dans la corbeille peut être supprimée définitivement
- Cette action est irréversible et demande une confirmation
- Une fois supprimée définitivement, l'entrée ne peut plus être récupérée

### Vider la corbeille

- Bouton "Vider la corbeille" pour supprimer toutes les entrées de la corbeille d'un coup
- Demande une confirmation avant la suppression définitive
- Affiche le nombre d'entrées supprimées

## Accès à la corbeille

1. Ouvrir le gestionnaire de mots de passe
2. Cliquer sur le bouton menu (⋮) en haut à droite
3. Sélectionner "Corbeille"

## Migration automatique

Lors de la première utilisation après la mise à jour :

- Une migration automatique ajoute la colonne `deleted_at` aux bases de données existantes
- Les entrées existantes ne sont pas affectées
- Aucune action manuelle n'est requise

## Comportement technique

### Base de données

- Nouvelle colonne : `deleted_at TIMESTAMP NULL`
- NULL = entrée active
- Date présente = entrée dans la corbeille

### API du repository

```python
# Déplacer vers la corbeille (soft delete)
repository.delete_entry(entry_id)

# Restaurer de la corbeille
repository.restore_entry(entry_id)

# Supprimer définitivement
repository.delete_entry_permanently(entry_id)

# Lister la corbeille
entries = repository.list_trash()

# Vider la corbeille
count = repository.empty_trash()
```

### API du service

```python
# Déplacer vers la corbeille
password_service.delete_entry(entry_id)

# Restaurer
password_service.restore_entry(entry_id)

# Supprimer définitivement
password_service.delete_entry_permanently(entry_id)

# Lister la corbeille
entries = password_service.list_trash()

# Vider la corbeille
count = password_service.empty_trash()
```

## Sécurité

- Les entrées dans la corbeille restent chiffrées
- Les mots de passe ne sont jamais stockés en clair
- La corbeille respecte l'isolation multi-utilisateurs
- Chaque utilisateur a sa propre corbeille

## Bonnes pratiques

1. **Vider régulièrement la corbeille** : Les entrées supprimées restent dans la base de données jusqu'à ce qu'elles soient définitivement supprimées
2. **Vérifier avant de vider** : Une fois la corbeille vidée, les données ne peuvent plus être récupérées
3. **Restaurer rapidement** : Si vous supprimez une entrée par erreur, restaurez-la immédiatement depuis la corbeille
