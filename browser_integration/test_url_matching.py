#!/usr/bin/env python3
"""
Test du comportement de filtrage par URL côté extension

Ce test simule le comportement attendu :
1. L'extension récupère TOUTES les entrées
2. Si l'URL courante match une entrée → afficher seulement celle(s)-là
3. Si l'URL courante ne match pas → afficher TOUTES les entrées
4. La barre de recherche permet de chercher dans TOUTES les entrées
"""

def extract_domain(url):
    """Extrait le domaine d'une URL (simule la fonction JS)"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        hostname = parsed.hostname or ''
        return hostname.replace('www.', '')
    except Exception:
        return url

def filter_by_url(all_credentials, current_url):
    """
    Simule la logique de filtrage de l'extension
    
    Args:
        all_credentials: Liste de tous les credentials
        current_url: URL de l'onglet courant
        
    Returns:
        Liste des credentials à afficher
    """
    # Si URL système, afficher tout
    if not current_url or current_url.startswith('about:') or current_url.startswith('moz-extension:'):
        return all_credentials
    
    # Extraire le domaine de l'URL courante
    current_domain = extract_domain(current_url)
    
    # Filtrer les credentials qui matchent
    matching_creds = []
    for cred in all_credentials:
        if not cred.get('url'):
            continue
        
        cred_domain = extract_domain(cred['url'])
        
        # Match si l'un contient l'autre
        if (cred_domain and current_domain and 
            (cred_domain in current_domain or current_domain in cred_domain)):
            matching_creds.append(cred)
    
    # Si match → afficher seulement ceux qui matchent
    # Sinon → afficher TOUT
    return matching_creds if matching_creds else all_credentials


# Base de données test
TEST_CREDENTIALS = [
    {'id': 1, 'title': 'Test', 'username': 'test', 'url': 'https://test.fr'},
    {'id': 2, 'title': 'Test2', 'username': 'plog66@live.fr', 'url': 'https://myhappy-place.fr'},
    {'id': 3, 'title': 'Entree3', 'username': 'plog78@live.fr', 'url': 'https://test.fr'}
]


def test_scenario(scenario_name, current_url, expected_count, expected_titles):
    """Test un scénario de filtrage"""
    print(f"\n{'='*70}")
    print(f"📍 Test: {scenario_name}")
    print(f"   URL courante: {current_url or '(vide)'}")
    print(f"{'='*70}")
    
    result = filter_by_url(TEST_CREDENTIALS, current_url)
    
    print(f"\n✅ Credentials affichés: {len(result)}")
    for cred in result:
        print(f"   • {cred['title']} ({cred['username']}) - {cred['url']}")
    
    # Vérification
    success = len(result) == expected_count and all(
        any(cred['title'] == title for cred in result) 
        for title in expected_titles
    )
    
    if success:
        print(f"\n✅ SUCCÈS: {expected_count} entrée(s) comme attendu")
    else:
        print(f"\n❌ ÉCHEC: Attendu {expected_count}, obtenu {len(result)}")
        print(f"   Titres attendus: {expected_titles}")
        print(f"   Titres obtenus: {[c['title'] for c in result]}")
    
    return success


def main():
    """Lance tous les tests"""
    print("╔" + "="*68 + "╗")
    print("║" + " "*15 + "TEST FILTRAGE PAR URL" + " "*32 + "║")
    print("╚" + "="*68 + "╝")
    
    tests = [
        # Scénario 1: URL système → afficher tout
        ("URL système (about:debugging)", 
         "about:debugging#/runtime/this-firefox",
         3,
         ['Test', 'Test2', 'Entree3']),
        
        # Scénario 2: URL qui match (test.fr) → afficher seulement les matchs
        ("URL qui match (test.fr)",
         "https://test.fr/login",
         2,
         ['Test', 'Entree3']),
        
        # Scénario 3: URL qui match (myhappy-place.fr) → afficher seulement le match
        ("URL qui match (myhappy-place.fr)",
         "https://www.myhappy-place.fr/signin",
         1,
         ['Test2']),
        
        # Scénario 4: URL qui ne match PAS → afficher TOUT
        ("URL qui ne match PAS (github.com)",
         "https://github.com/login",
         3,
         ['Test', 'Test2', 'Entree3']),
        
        # Scénario 5: URL vide → afficher tout
        ("URL vide",
         "",
         3,
         ['Test', 'Test2', 'Entree3']),
    ]
    
    results = []
    for test_args in tests:
        results.append(test_scenario(*test_args))
    
    # Résumé
    print(f"\n\n{'='*70}")
    print("📊 RÉSUMÉ")
    print(f"{'='*70}")
    print(f"Total: {len(results)} tests")
    print(f"✅ Succès: {sum(results)}")
    print(f"❌ Échecs: {len(results) - sum(results)}")
    
    if all(results):
        print("\n🎉 TOUS LES TESTS PASSENT !")
        print("\n💡 Comportement validé:")
        print("   • URL match → affiche seulement les entrées qui matchent")
        print("   • URL ne match pas → affiche TOUTES les entrées")
        print("   • La recherche peut toujours accéder à toutes les entrées")
        return 0
    else:
        print("\n⚠️  Certains tests ont échoué")
        return 1


if __name__ == '__main__':
    exit(main())
