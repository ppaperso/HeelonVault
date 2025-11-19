# 🌐 Guide du champ URL

## 📋 Vue d'ensemble

Le champ URL permet de stocker l'adresse web associée à une entrée de mot de passe, facilitant l'accès direct aux services web.

## ✨ Fonctionnalités

### 1️⃣ Dans le formulaire de création/édition

**Emplacement** : Après le champ "Mot de passe"

**Caractéristiques** :
- 🌐 **Icône visuelle** pour identification rapide
- 📝 **Label** : "🌐 URL (optionnel)"
- 💡 **Placeholder** : `https://exemple.com`
- 📖 **Texte d'aide** : "Pour les sites web, entrez l'URL de connexion"
- ✅ **Optionnel** : Pas de validation requise

**Exemples d'utilisation** :
```
Gmail         : mail.google.com
Facebook      : facebook.com
GitHub        : github.com/login
Banque        : www.mabanque.fr/espace-client
```

### 2️⃣ Dans l'affichage des détails

**Boutons disponibles** :

| Icône | Tooltip | Fonction |
|-------|---------|----------|
| 📋 | Copier dans le presse-papiers | Copie l'URL |
| 🌐 | Ouvrir dans le navigateur | Ouvre l'URL avec xdg-open |

**Comportement** :
- L'URL n'est affichée que si elle est renseignée
- Ajout automatique de `https://` si manquant lors de l'ouverture
- Gestion d'erreur si impossible d'ouvrir

### 3️⃣ Dans la recherche

Le champ URL est **inclus dans la recherche globale** :

```python
# Recherche dans : titre, nom d'utilisateur ET URL
search_pattern = f'%{search_text}%'
cursor.execute('''
    SELECT * FROM passwords 
    WHERE title LIKE ? OR username LIKE ? OR url LIKE ?
''', (search_pattern, search_pattern, search_pattern))
```

**Exemple** :
- Recherche "google" → Trouve toutes les entrées avec "google" dans l'URL

## 🗄️ Structure de la base de données

```sql
CREATE TABLE passwords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    username TEXT,
    password_data TEXT NOT NULL,
    url TEXT,                      -- Champ URL
    notes TEXT,
    category TEXT,
    tags TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Type** : `TEXT` (chaîne de caractères, NULL autorisé)

## 📦 Modèle de données

```python
@dataclass
class PasswordEntry:
    """Entrée de mot de passe"""
    title: str
    username: str
    password: str
    url: str = ""           # Champ URL optionnel
    notes: str = ""
    category: str = ""
    tags: List[str] = field(default_factory=list)
    # ...
    
    def matches_search(self, search_text: str) -> bool:
        """Recherche dans titre, username ET url"""
        search_lower = search_text.lower()
        return (
            search_lower in self.title.lower() or
            search_lower in self.username.lower() or
            search_lower in self.url.lower()    # Inclus dans la recherche
        )
```

## 💻 Code source

### Ajout d'une entrée avec URL

```python
def add_entry(self, title: str, username: str, password: str, 
              url: str = "", notes: str = "", category: str = "", 
              tags: list = None):
    """Ajoute une entrée avec URL optionnelle"""
    # Chiffrement du mot de passe
    encrypted_pass = self.crypto.encrypt(password)
    
    # Insertion avec URL
    cursor.execute('''
        INSERT INTO passwords 
        (title, username, password_data, url, notes, category, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (title, username, encrypted_pass, url, notes, category, tags_json))
```

### Ouverture de l'URL dans le navigateur

```python
def open_url(self, url):
    """Ouvre une URL dans le navigateur par défaut"""
    import subprocess
    
    # Ajout automatique de https:// si manquant
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        # xdg-open sur Linux
        subprocess.Popen(['xdg-open', url], 
                       stdout=subprocess.DEVNULL, 
                       stderr=subprocess.DEVNULL)
    except Exception as e:
        # Affichage d'erreur à l'utilisateur
        self.show_error(f"Impossible d'ouvrir l'URL : {e}")
```

### Affichage du champ URL

```python
# Dans la vue détaillée
if entry['url']:
    url_box = self.create_field_box(
        "URL", 
        entry['url'], 
        copyable=True,    # Bouton copier
        is_url=True       # Bouton ouvrir navigateur
    )
    self.detail_box.append(url_box)
```

## 📝 Exemples d'utilisation

### Cas d'usage 1 : Compte email

```
Titre: Gmail Personnel
Catégorie: Email
Nom d'utilisateur: john.doe@gmail.com
Mot de passe: ••••••••••••
URL: mail.google.com
Notes: Compte principal
```

**Avantages** :
- Clic sur 🌐 → Ouvre Gmail directement
- Pas besoin de chercher l'URL dans un navigateur

### Cas d'usage 2 : Réseau social

```
Titre: LinkedIn
Catégorie: Réseaux sociaux
Nom d'utilisateur: john.doe
Mot de passe: ••••••••••••
URL: linkedin.com
Tags: professionnel, emploi
```

### Cas d'usage 3 : Banque en ligne

```
Titre: Crédit Agricole
Catégorie: Banque
Nom d'utilisateur: 123456789
Mot de passe: ••••••••••••
URL: www.credit-agricole.fr/particulier/acceder-a-mes-comptes.html
Notes: Code carte : XXXX
```

### Cas d'usage 4 : Code PIN (sans URL)

```
Titre: Code PIN téléphone
Catégorie: Personnel
Mot de passe: 1234
URL:                  ← Laissé vide (pas d'URL)
Notes: Code de déverrouillage
```

**Comportement** : Champ URL non affiché dans les détails

## 🔒 Sécurité

### Stockage
- ✅ **URL stockée en clair** (pas chiffrée)
- ✅ **Raison** : Nécessaire pour la recherche et l'affichage
- ⚠️ **Note** : Ne pas mettre d'informations sensibles dans l'URL

### Ouverture sécurisée
- ✅ **Validation du protocole** : http:// ou https://
- ✅ **Pas d'exécution de code** : Utilise xdg-open (safe)
- ✅ **Gestion d'erreur** : Affichage à l'utilisateur si échec

## 🎨 Interface utilisateur

### Formulaire

```
┌─────────────────────────────────────────┐
│ 🌐 URL (optionnel)                      │
│ ┌─────────────────────────────────────┐ │
│ │ https://exemple.com                 │ │
│ └─────────────────────────────────────┘ │
│ Pour les sites web, entrez l'URL de     │
│ connexion                                │
└─────────────────────────────────────────┘
```

### Vue détaillée

```
┌─────────────────────────────────────────┐
│ URL                                      │
│ ┌──────────────────────────────┐ 📋 🌐 │
│ │ mail.google.com              │        │
│ └──────────────────────────────┘        │
│   ↑ Non éditable    Copier ↑  ↑ Ouvrir │
└─────────────────────────────────────────┘
```

## 🧪 Tests

### Test 1 : Création avec URL complète
```bash
1. Créer une entrée avec : https://mail.google.com
2. Vérifier l'enregistrement
3. Cliquer sur 🌐 → Doit ouvrir le navigateur
```

### Test 2 : Création avec URL partielle
```bash
1. Créer une entrée avec : mail.google.com
2. Cliquer sur 🌐 → Doit ouvrir https://mail.google.com
```

### Test 3 : Création sans URL
```bash
1. Créer une entrée sans URL
2. Vérifier que le champ URL n'apparaît pas dans les détails
```

### Test 4 : Recherche par URL
```bash
1. Créer plusieurs entrées avec URLs différentes
2. Rechercher "google"
3. Vérifier que seules les entrées avec "google" dans l'URL apparaissent
```

### Test 5 : Copie de l'URL
```bash
1. Afficher une entrée avec URL
2. Cliquer sur 📋
3. Coller dans un éditeur → Doit contenir l'URL
```

## 🚀 Améliorations futures possibles

- [ ] Favicon automatique à partir de l'URL
- [ ] Validation de l'URL (format correct)
- [ ] Historique des URLs visitées
- [ ] Extraction automatique du domaine
- [ ] QR Code de l'URL
- [ ] Raccourci clavier pour ouvrir (Ctrl+O)
- [ ] Liste des URLs récentes
- [ ] Détection automatique d'URL dans le presse-papiers

## 📚 Ressources

### Fichiers concernés
```
password_manager.py
├── PasswordDatabase.add_entry()       (ligne 386)
├── PasswordDatabase.get_all_entries() (ligne 402)
├── PasswordManagerApp.create_field_box() (ligne 1092)
├── PasswordManagerApp.open_url()      (ligne 1128)
└── AddEditDialog.__init__()           (ligne 1293)

src/models/password_entry.py
└── PasswordEntry.url                  (ligne 27)
```

### Standards web
- [URL Standard (WHATWG)](https://url.spec.whatwg.org/)
- [RFC 3986 - URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986)

---

**Version** : 2.1  
**Dernière mise à jour** : 19 novembre 2025  
**Statut** : ✅ Fonctionnel et testé
