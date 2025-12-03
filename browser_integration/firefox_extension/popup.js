/**
 * Popup Script pour l'extension Password Manager
 * Interface utilisateur pour rechercher et gérer les mots de passe
 */

let currentTab = null;
let allCredentials = [];

/**
 * Initialisation
 */
document.addEventListener('DOMContentLoaded', async () => {
  console.log("Popup initialisé");
  
  // Récupérer l'onglet actif
  const tabs = await browser.tabs.query({active: true, currentWindow: true});
  currentTab = tabs[0];
  
  // Vérifier le statut de connexion
  checkConnectionStatus();
  
  // Charger les credentials pour le site actuel
  loadCredentials();
  
  // Event listeners
  document.getElementById('searchInput').addEventListener('input', handleSearch);
  document.getElementById('generateBtn').addEventListener('click', generatePassword);
  document.getElementById('copyPasswordBtn').addEventListener('click', copyGeneratedPassword);
  document.getElementById('refreshBtn').addEventListener('click', loadCredentials);
  document.getElementById('settingsBtn').addEventListener('click', openSettings);
});

/**
 * Vérifie le statut de connexion au native host
 */
async function checkConnectionStatus() {
  const statusIndicator = document.querySelector('.status-indicator');
  const statusText = document.querySelector('.status-text');
  
  try {
    const response = await browser.runtime.sendMessage({
      type: "checkStatus"
    });
    
    if (response.status === "success") {
      statusIndicator.className = 'status-indicator connected';
      statusText.textContent = 'Connecté';
    } else {
      statusIndicator.className = 'status-indicator disconnected';
      statusText.textContent = 'Déconnecté';
    }
  } catch (error) {
    console.error("Erreur de connexion:", error);
    statusIndicator.className = 'status-indicator disconnected';
    statusText.textContent = 'Erreur';
  }
}

/**
 * Charge les credentials pour le site actuel
 */
async function loadCredentials() {
  const list = document.getElementById('credentialsList');
  const emptyState = document.querySelector('.empty-state');
  
  list.innerHTML = '<div class="loading">Chargement...</div>';
  emptyState.style.display = 'none';
  
  try {
    // Toujours récupérer TOUTES les entrées
    const response = await browser.runtime.sendMessage({
      type: "searchCredentials",
      url: '',
      showAll: true  // Toujours demander toutes les entrées
    });
    
    if (response.status === "success") {
      allCredentials = response.credentials || [];
      
      // Filtrer côté client selon l'URL de l'onglet actuel
      let credentialsToDisplay = allCredentials;
      
      if (currentTab && currentTab.url && !currentTab.url.startsWith('about:') && !currentTab.url.startsWith('moz-extension:')) {
        // Extraire le domaine de l'URL courante
        const currentDomain = extractDomain(currentTab.url);
        
        // Filtrer les credentials qui matchent le domaine
        const matchingCreds = allCredentials.filter(cred => {
          if (!cred.url) return false;
          const credDomain = extractDomain(cred.url);
          return credDomain && currentDomain && credDomain.includes(currentDomain) || currentDomain.includes(credDomain);
        });
        
        // Si des credentials matchent, afficher seulement ceux-là
        // Sinon, afficher TOUT pour permettre la recherche manuelle
        credentialsToDisplay = matchingCreds.length > 0 ? matchingCreds : allCredentials;
      }
      
      displayCredentials(credentialsToDisplay);
    } else {
      list.innerHTML = '<div class="error">Erreur lors du chargement</div>';
    }
  } catch (error) {
    console.error("Erreur:", error);
    list.innerHTML = '<div class="error">Erreur de connexion</div>';
  }
}

/**
 * Extrait le domaine d'une URL
 */
function extractDomain(url) {
  try {
    const urlObj = new URL(url);
    return urlObj.hostname.replace('www.', '');
  } catch (e) {
    return url;
  }
}

/**
 * Affiche la liste des credentials
 */
function displayCredentials(credentials) {
  const list = document.getElementById('credentialsList');
  const emptyState = document.querySelector('.empty-state');
  
  if (credentials.length === 0) {
    list.innerHTML = '';
    emptyState.style.display = 'block';
    return;
  }
  
  emptyState.style.display = 'none';
  list.innerHTML = '';
  
  credentials.forEach(cred => {
    const item = document.createElement('div');
    item.className = 'credential-item';
    
    const info = document.createElement('div');
    info.className = 'credential-info';
    info.innerHTML = `
      <div class="credential-title">${escapeHtml(cred.title || cred.url)}</div>
      <div class="credential-username">${escapeHtml(cred.username)}</div>
    `;
    
    const actions = document.createElement('div');
    actions.className = 'credential-actions';
    
    const fillBtn = document.createElement('button');
    fillBtn.className = 'action-btn';
    fillBtn.textContent = '🔑 Remplir';
    fillBtn.title = 'Remplir les champs';
    fillBtn.addEventListener('click', () => fillCredential(cred));
    
    const copyBtn = document.createElement('button');
    copyBtn.className = 'action-btn';
    copyBtn.textContent = '📋';
    copyBtn.title = 'Copier le mot de passe';
    copyBtn.addEventListener('click', () => copyCredential(cred));
    
    actions.appendChild(fillBtn);
    actions.appendChild(copyBtn);
    
    item.appendChild(info);
    item.appendChild(actions);
    list.appendChild(item);
  });
}

/**
 * Remplit les champs avec un credential
 */
async function fillCredential(cred) {
  try {
    // Injecter un script dans la page pour remplir les champs
    await browser.tabs.executeScript(currentTab.id, {
      code: `
        (function() {
          const passwordField = document.querySelector('input[type="password"]');
          const usernameField = document.querySelector('input[type="text"], input[type="email"]');
          
          if (usernameField) usernameField.value = '${cred.username.replace(/'/g, "\\'")}';
          if (passwordField) {
            // Le mot de passe sera récupéré via le content script
            window.postMessage({ type: 'PM_FILL', credId: '${cred.id}' }, '*');
          }
        })();
      `
    });
    
    showNotification('Identifiants remplis', 'success');
    window.close();
  } catch (error) {
    console.error("Erreur:", error);
    showNotification('Erreur lors du remplissage', 'error');
  }
}

/**
 * Copie le mot de passe d'un credential
 */
async function copyCredential(cred) {
  try {
    const response = await browser.runtime.sendMessage({
      type: "getCredentials",
      entryId: cred.id
    });
    
    if (response.status === "success") {
      // Copier dans le presse-papiers
      await navigator.clipboard.writeText(response.password);
      showNotification('Mot de passe copié', 'success');
    } else {
      showNotification('Erreur lors de la récupération', 'error');
    }
  } catch (error) {
    console.error("Erreur:", error);
    showNotification('Erreur de copie', 'error');
  }
}

/**
 * Génère un mot de passe
 */
async function generatePassword() {
  const generatedSection = document.getElementById('generatedPassword');
  const passwordText = document.getElementById('generatedPasswordText');
  
  try {
    const response = await browser.runtime.sendMessage({
      type: "generatePassword",
      length: 20
    });
    
    if (response.status === "success") {
      passwordText.value = response.password;
      generatedSection.style.display = 'block';
      showNotification('Mot de passe généré', 'success');
    } else {
      showNotification('Erreur de génération', 'error');
    }
  } catch (error) {
    console.error("Erreur:", error);
    showNotification('Erreur de connexion', 'error');
  }
}

/**
 * Copie le mot de passe généré
 */
async function copyGeneratedPassword() {
  const passwordText = document.getElementById('generatedPasswordText');
  
  try {
    await navigator.clipboard.writeText(passwordText.value);
    showNotification('Mot de passe copié', 'success');
  } catch (error) {
    console.error("Erreur:", error);
    showNotification('Erreur de copie', 'error');
  }
}

/**
 * Gère la recherche
 * Cherche toujours dans TOUTES les entrées (allCredentials)
 */
function handleSearch(e) {
  const query = e.target.value.toLowerCase();
  
  if (query === '') {
    // Recharger avec filtrage par URL
    loadCredentials();
    return;
  }
  
  // Chercher dans TOUTES les entrées disponibles
  const filtered = allCredentials.filter(cred => {
    return (cred.title && cred.title.toLowerCase().includes(query)) ||
           (cred.username && cred.username.toLowerCase().includes(query)) ||
           (cred.url && cred.url.toLowerCase().includes(query));
  });
  
  displayCredentials(filtered);
}

/**
 * Ouvre les paramètres
 */
function openSettings() {
  // TODO: Créer une page de paramètres
  alert('Paramètres à venir dans une prochaine version');
}

/**
 * Affiche une notification
 */
function showNotification(message, type = 'info') {
  // Créer une notification toast
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: ${type === 'success' ? '#4CAF50' : type === 'error' ? '#f44336' : '#2196F3'};
    color: white;
    padding: 10px 20px;
    border-radius: 4px;
    z-index: 1000;
    animation: slideUp 0.3s ease;
  `;
  
  document.body.appendChild(toast);
  
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, 2000);
}

/**
 * Échappe le HTML
 */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}
