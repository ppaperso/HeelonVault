# 🔍 Comportement de Filtrage par URL de l'Extension

## Logique Implémentée

### Principe
L'extension récupère **TOUJOURS** toutes les entrées de la base de données, puis applique un **filtrage intelligent côté client** selon l'URL de l'onglet courant.

### Règles de Filtrage

#### 1️⃣ URL Système (about:, moz-extension:)
- **Affiche:** TOUTES les entrées (3 entrées)
- **Raison:** Pas de contexte web, l'utilisateur veut parcourir sa liste complète
- **Exemple:** `about:debugging#/runtime/this-firefox`

#### 2️⃣ URL Match Une ou Plusieurs Entrées
- **Affiche:** UNIQUEMENT les entrées correspondantes
- **Raison:** Contextuel, facilite la sélection rapide
- **Exemples:**
  - Sur `https://test.fr/login` → Affiche 2 entrées (Test et Entree3)
  - Sur `https://myhappy-place.fr/signin` → Affiche 1 entrée (Test2)

#### 3️⃣ URL Ne Match AUCUNE Entrée
- **Affiche:** TOUTES les entrées (3 entrées)
- **Raison:** Permet de choisir manuellement ou de créer une nouvelle entrée
- **Exemple:** Sur `https://github.com/login` → Affiche toutes les 3 entrées

### Barre de Recherche

- **Cherche dans:** TOUTES les entrées (allCredentials)
- **Fonction:** Filtre en temps réel par titre, username ou URL
- **Comportement:** Quand la recherche est vidée → retour au filtrage par URL

## Avantages de cette Approche

### ✅ Meilleure Expérience Utilisateur
1. **Contextuel:** Sur un site connu, affiche directement les bons identifiants
2. **Flexible:** Sur un site inconnu, l'utilisateur peut quand même choisir
3. **Recherche puissante:** La barre de recherche donne accès à tout

### ✅ Pas de Blocage
- Jamais bloqué sur une seule entrée
- Toujours possible de chercher et sélectionner une autre entrée
- La recherche "débloque" le filtrage par URL

### ✅ Performance
- Une seule requête au backend (récupère tout)
- Filtrage rapide en JavaScript côté client
- Pas de requête supplémentaire pour la recherche

## Exemples Concrets

### Scénario A: Test depuis about:debugging
```
URL: about:debugging#/runtime/this-firefox
Affichage initial:
  🔑 Entree3 (plog78@live.fr)
  🔑 Test (test)
  🔑 Test2 (plog66@live.fr)

→ L'utilisateur voit tout sa liste pour tester
```

### Scénario B: Visite de test.fr
```
URL: https://test.fr/login
Affichage initial:
  🔑 Test (test)
  🔑 Entree3 (plog78@live.fr)

→ Seulement les entrées pertinentes

Si l'utilisateur tape "plog66" dans la recherche:
  🔑 Test2 (plog66@live.fr)

→ Peut quand même accéder aux autres entrées via la recherche
```

### Scénario C: Visite de github.com (pas dans la BDD)
```
URL: https://github.com/login
Affichage initial:
  🔑 Entree3 (plog78@live.fr)
  🔑 Test (test)
  🔑 Test2 (plog66@live.fr)

→ Toutes les entrées disponibles car aucune ne correspond
→ L'utilisateur peut choisir ou créer une nouvelle entrée
```

## Implémentation Technique

### Côté Extension (popup.js)

```javascript
async function loadCredentials() {
  // 1. Récupérer TOUTES les entrées
  const response = await browser.runtime.sendMessage({
    type: "searchCredentials",
    url: '',
    showAll: true
  });
  
  allCredentials = response.credentials || [];
  
  // 2. Filtrage côté client
  let credentialsToDisplay = allCredentials;
  
  if (currentTab && currentTab.url && !isSystemURL(currentTab.url)) {
    const currentDomain = extractDomain(currentTab.url);
    const matchingCreds = allCredentials.filter(cred => {
      const credDomain = extractDomain(cred.url);
      return domainMatches(credDomain, currentDomain);
    });
    
    // Si match → afficher seulement les matchs
    // Sinon → afficher TOUT
    credentialsToDisplay = matchingCreds.length > 0 
      ? matchingCreds 
      : allCredentials;
  }
  
  displayCredentials(credentialsToDisplay);
}
```

### Côté Backend (native_host.py)

```python
def _search_in_database(self, url, show_all=False):
    if show_all or not url:
        # Récupérer TOUT sans filtrage
        cursor.execute('''
            SELECT id, title, username, url, category 
            FROM passwords 
            ORDER BY title
        ''')
    else:
        # (Cette branche n'est plus utilisée par l'extension)
        # mais gardée pour compatibilité
        ...
```

## Tests de Validation

Tous les scénarios sont testés dans `test_url_matching.py` :

```bash
$ python3 test_url_matching.py

✅ URL système (about:debugging) → 3 entrées
✅ URL qui match (test.fr) → 2 entrées
✅ URL qui match (myhappy-place.fr) → 1 entrée
✅ URL qui ne match PAS (github.com) → 3 entrées
✅ URL vide → 3 entrées

🎉 TOUS LES TESTS PASSENT !
```

## Fichiers Modifiés

- ✅ `firefox_extension_dev/popup.js` - Logique DEV
- ✅ `firefox_extension/popup.js` - Logique PROD
- ✅ `native_host.py` - Support showAll (déjà fait)
- ✅ `test_url_matching.py` - Tests de validation

## Utilisation

### Recharger l'Extension

1. Firefox: `about:debugging#/runtime/this-firefox`
2. Trouver "Password Manager DEV"
3. Cliquer "Recharger" 🔄

### Tester les Scénarios

**Test 1: Sur about:debugging**
- Ouvrir le popup → Voir les 3 entrées

**Test 2: Aller sur https://test.fr**
- Ouvrir le popup → Voir 2 entrées (Test et Entree3)
- Taper "plog66" dans la recherche → Voir Test2 aussi

**Test 3: Aller sur https://github.com**
- Ouvrir le popup → Voir les 3 entrées (aucune ne match)

## Prochaines Étapes

1. ✅ Filtrage intelligent implémenté
2. ⏳ Test en situation réelle dans Firefox
3. 🔜 Implémentation de la récupération réelle des mots de passe
4. 🔜 Auto-fill des formulaires web
5. 🔜 Sauvegarde de nouveaux identifiants

---

**Date:** 3 décembre 2025  
**Version:** 0.1.0-beta  
**Statut:** ✅ Implémenté et testé
