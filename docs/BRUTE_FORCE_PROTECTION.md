# Protection Anti-Brute Force

## Vue d'ensemble

La protection contre les attaques par force brute a été implémentée pour sécuriser la page de connexion. Elle combine plusieurs techniques de défense :

## Fonctionnalités

### 1. Délai Progressif
Après chaque tentative de connexion échouée, un délai croissant est imposé :
- 1ère tentative échouée : délai de 1 seconde
- 2ème tentative échouée : délai de 2 secondes
- 3ème tentative échouée : délai de 4 secondes
- 4ème tentative échouée : délai de 8 secondes
- 5ème tentative échouée : délai de 16 secondes
- Maximum : 32 secondes

### 2. Verrouillage Temporaire
Après **5 tentatives échouées**, le compte est verrouillé pendant **15 minutes**.

### 3. Journalisation des Tentatives
Toutes les tentatives de connexion sont enregistrées dans un fichier journal :
- **Emplacement** : `~/.local/share/passwordmanager/security.log`
- **Contenu** :
  - Tentatives échouées avec compteur
  - Verrouillages de comptes
  - Connexions réussies
  - Timestamps et niveaux de log

## Architecture

### Service `LoginAttemptTracker`
**Fichier** : `src/services/login_attempt_tracker.py`

Service singleton qui gère :
- Le suivi des tentatives par utilisateur
- Le calcul des délais progressifs
- La gestion des verrouillages temporaires
- La journalisation des événements de sécurité

### Intégration UI
**Fichier** : `src/ui/dialogs/login_dialog.py`

Le dialogue de connexion a été modifié pour :
- Vérifier les autorisations avant chaque tentative
- Désactiver l'interface pendant les délais/verrouillages
- Afficher des messages informatifs à l'utilisateur
- Mettre à jour dynamiquement le temps restant

## Configuration

Les paramètres de protection sont définis dans `LoginAttemptTracker` :

```python
MAX_ATTEMPTS_BEFORE_LOCKOUT = 5      # Nombre max de tentatives
LOCKOUT_DURATION_SECONDS = 900        # 15 minutes de verrouillage
BASE_DELAY_SECONDS = 1                # Délai de base
MAX_DELAY_SECONDS = 32                # Délai maximum
```

## Messages Utilisateur

L'utilisateur voit différents messages selon la situation :

- ❌ **Mot de passe incorrect** (première tentative)
- ❌ **Mot de passe incorrect (prochaine tentative dans Xs)** (avec délai)
- ⏳ **Veuillez patienter Xs avant de réessayer** (délai en cours)
- 🔒 **Trop de tentatives échouées. Veuillez patienter X min** (verrouillé)

## Journalisation

Exemple de logs de sécurité :

```
2025-11-19 10:15:23 - WARNING - Tentative de connexion échouée pour 'alice' (tentative 1/5)
2025-11-19 10:15:25 - WARNING - Tentative de connexion échouée pour 'alice' (tentative 2/5)
2025-11-19 10:15:30 - WARNING - Tentative de connexion échouée pour 'alice' (tentative 3/5)
2025-11-19 10:15:38 - WARNING - Tentative de connexion échouée pour 'alice' (tentative 4/5)
2025-11-19 10:15:54 - WARNING - Tentative de connexion échouée pour 'alice' (tentative 5/5)
2025-11-19 10:15:54 - ERROR - 🔒 VERROUILLAGE: Compte 'alice' verrouillé pendant 15 minutes
2025-11-19 10:30:54 - INFO - Fin du verrouillage pour 'alice'
2025-11-19 10:31:02 - INFO - ✅ Connexion réussie pour 'alice' (après 1 tentative(s) échouée(s))
```

## Tests

Suite de tests complète : `tests/integration/test_brute_force_protection.py`

**Tests couverts** :
- ✅ Premier essai toujours autorisé
- ✅ Délai progressif fonctionnel
- ✅ Verrouillage après 5 tentatives
- ✅ Réinitialisation après succès
- ✅ Calcul correct des délais
- ✅ Indépendance entre utilisateurs
- ✅ Réinitialisation globale

**Exécution** :
```bash
python -m unittest tests.integration.test_brute_force_protection -v
```

## Sécurité

### Protection contre :
- ✅ Attaques par force brute (essais multiples rapides)
- ✅ Attaques par dictionnaire (ralentissement progressif)
- ✅ Attaques distribuées (verrouillage par compte)

### Limitations :
- Les compteurs sont en mémoire (réinitialisés au redémarrage)
- Pas de blocage par IP (pas d'authentification réseau)
- Pas de notification admin en temps réel

### Recommandations :
1. Surveiller régulièrement `security.log`
2. Utiliser des mots de passe forts
3. Changer les mots de passe par défaut
4. Considérer l'ajout d'authentification à deux facteurs

## API

### Vérifier autorisation
```python
can_attempt, remaining = tracker.check_can_attempt(username)
```

### Enregistrer échec
```python
tracker.record_failed_attempt(username)
```

### Enregistrer succès
```python
tracker.record_successful_attempt(username)
```

### Obtenir informations
```python
info = tracker.get_attempt_info(username)
if info:
    print(f"Tentatives: {info.failed_attempts}")
    print(f"Verrouillé jusqu'à: {info.lockout_until}")
```

## Impact Performance

- **Mémoire** : ~200 bytes par utilisateur avec tentatives
- **CPU** : Négligeable (calculs simples)
- **Disque** : Logs incrementaux (~1 KB/jour en utilisation normale)

## Maintenance

Le service est auto-géré :
- Les verrouillages expirent automatiquement
- Les compteurs sont réinitialisés après succès
- Aucune maintenance manuelle requise

Pour réinitialiser tous les compteurs (tests/debug) :
```python
tracker.clear_all_attempts()
```
