"""
Tests unitaires pour le service d'importation CSV
"""

import unittest
import tempfile
from pathlib import Path
from src.services.csv_importer import CSVImporter


class TestCSVImporter(unittest.TestCase):
    """Tests du service d'importation CSV"""
    
    def setUp(self):
        """Initialisation avant chaque test"""
        self.importer = CSVImporter()
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Nettoyage après chaque test"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_lastpass_format(self):
        """Teste l'import du format LastPass"""
        # Créer un fichier CSV de test
        csv_content = """https://github.com;john.doe@email.com;MySecretPass123!;GitHub Account
https://gmail.com;jane.smith@gmail.com;Gmail2024Secure;Gmail Personnel
https://twitter.com;@myhandle;Tw1tt3rP@ss;Twitter"""
        
        csv_file = Path(self.temp_dir) / "test_lastpass.csv"
        csv_file.write_text(csv_content, encoding='utf-8')
        
        # Importer
        result = self.importer.import_from_csv(csv_file, format_name='lastpass')
        
        # Vérifications
        self.assertTrue(result['success'])
        self.assertEqual(len(result['entries']), 3)
        
        # Vérifier la première entrée
        entry1 = result['entries'][0]
        self.assertEqual(entry1['url'], 'https://github.com')
        self.assertEqual(entry1['username'], 'john.doe@email.com')
        self.assertEqual(entry1['password'], 'MySecretPass123!')
        self.assertEqual(entry1['name'], 'GitHub Account')
        self.assertEqual(entry1['category'], 'Importé')
        self.assertIn('import', entry1['tags'])
    
    def test_lastpass_with_header(self):
        """Teste l'import LastPass avec ligne d'en-tête"""
        csv_content = """url;username;password;name
https://github.com;john.doe@email.com;MySecretPass123!;GitHub Account
https://gmail.com;jane.smith@gmail.com;Gmail2024Secure;Gmail Personnel"""
        
        csv_file = Path(self.temp_dir) / "test_with_header.csv"
        csv_file.write_text(csv_content, encoding='utf-8')
        
        # Importer avec en-tête
        result = self.importer.import_from_csv(csv_file, format_name='lastpass', has_header=True)
        
        # Vérifications
        self.assertTrue(result['success'])
        self.assertEqual(len(result['entries']), 2)  # L'en-tête ne doit pas être importée
    
    def test_generic_comma_format(self):
        """Teste l'import avec délimiteur virgule"""
        csv_content = """https://example.com,user1,pass1,Example Site
https://test.com,user2,pass2,Test Site"""
        
        csv_file = Path(self.temp_dir) / "test_comma.csv"
        csv_file.write_text(csv_content, encoding='utf-8')
        
        # Importer
        result = self.importer.import_from_csv(csv_file, format_name='generic_comma')
        
        # Vérifications
        self.assertTrue(result['success'])
        self.assertEqual(len(result['entries']), 2)
    
    def test_auto_detect_format(self):
        """Teste la détection automatique du format"""
        csv_content = """https://github.com;john.doe@email.com;MySecretPass123!;GitHub Account"""
        
        csv_file = Path(self.temp_dir) / "test_auto.csv"
        csv_file.write_text(csv_content, encoding='utf-8')
        
        # Détection automatique
        detected_format = self.importer.detect_format(csv_file)
        self.assertEqual(detected_format, 'lastpass')
        
        # Import avec auto-détection
        result = self.importer.import_from_csv(csv_file)
        self.assertTrue(result['success'])
        self.assertEqual(len(result['entries']), 1)
    
    def test_empty_fields(self):
        """Teste le traitement des champs vides"""
        csv_content = """https://example.com;;mypassword;Site Without Username
;user@email.com;pass123;Entry Without URL
https://test.com;testuser;;Entry Without Password"""
        
        csv_file = Path(self.temp_dir) / "test_empty.csv"
        csv_file.write_text(csv_content, encoding='utf-8')
        
        # Importer
        result = self.importer.import_from_csv(csv_file, format_name='lastpass')
        
        # Vérifications
        self.assertTrue(result['success'])
        self.assertEqual(len(result['entries']), 3)
        
        # Vérifier que les champs vides sont gérés
        self.assertEqual(result['entries'][0]['username'], '')
        self.assertEqual(result['entries'][1]['url'], '')
        self.assertEqual(result['entries'][2]['password'], '')
        
        # Devrait avoir des avertissements pour les mots de passe vides
        self.assertGreater(len(result['warnings']), 0)
    
    def test_missing_name_field(self):
        """Teste le traitement d'une entrée sans nom"""
        csv_content = """https://example.com;user1;pass1;
https://test.com;user2;pass2;Test Site"""
        
        csv_file = Path(self.temp_dir) / "test_no_name.csv"
        csv_file.write_text(csv_content, encoding='utf-8')
        
        # Importer
        result = self.importer.import_from_csv(csv_file, format_name='lastpass')
        
        # Vérifications
        self.assertTrue(result['success'])
        self.assertEqual(len(result['entries']), 2)
        
        # Le nom par défaut devrait être généré
        self.assertIn('Entrée importée', result['entries'][0]['name'])
        
        # Devrait avoir un avertissement
        self.assertGreater(len(result['warnings']), 0)
    
    def test_invalid_file(self):
        """Teste le traitement d'un fichier invalide"""
        csv_file = Path(self.temp_dir) / "nonexistent.csv"
        
        # Tenter d'importer un fichier inexistant
        result = self.importer.import_from_csv(csv_file, format_name='lastpass')
        
        # Vérifications
        self.assertFalse(result['success'])
        self.assertGreater(len(result['errors']), 0)
    
    def test_unsupported_format(self):
        """Teste le traitement d'un format non supporté"""
        csv_content = """test"""
        csv_file = Path(self.temp_dir) / "test.csv"
        csv_file.write_text(csv_content, encoding='utf-8')
        
        # Tenter d'importer avec un format invalide
        result = self.importer.import_from_csv(csv_file, format_name='invalid_format')
        
        # Vérifications
        self.assertFalse(result['success'])
        self.assertGreater(len(result['errors']), 0)
    
    def test_get_supported_formats(self):
        """Teste la récupération des formats supportés"""
        formats = CSVImporter.get_supported_formats()
        
        # Vérifications
        self.assertIsInstance(formats, dict)
        self.assertIn('lastpass', formats)
        self.assertIn('generic_comma', formats)
        self.assertIn('generic_semicolon', formats)
        
        # Vérifier que chaque format a une description
        for format_name, description in formats.items():
            self.assertIsInstance(description, str)
            self.assertGreater(len(description), 0)
    
    def test_special_characters(self):
        """Teste le traitement des caractères spéciaux"""
        csv_content = """https://example.com;user@email.com;P@ssWörd123!;Site spécial"""
        
        csv_file = Path(self.temp_dir) / "test_special.csv"
        csv_file.write_text(csv_content, encoding='utf-8')
        
        # Importer
        result = self.importer.import_from_csv(csv_file, format_name='lastpass')
        
        # Vérifications
        self.assertTrue(result['success'])
        self.assertEqual(len(result['entries']), 1)
        
        # Vérifier que les caractères spéciaux sont préservés
        entry = result['entries'][0]
        self.assertIn('ö', entry['password'])
        self.assertIn('spécial', entry['name'])


if __name__ == '__main__':
    unittest.main()
