/**
 * Content Script pour détecter les formulaires de connexion
 * S'exécute sur toutes les pages pour proposer l'auto-fill
 */

(function() {
  'use strict';
  
  console.log("Password Manager content script loaded");
  
  // État
  let formData = {
    usernameField: null,
    passwordField: null,
    form: null
  };
  
  /**
   * Détecte les champs de formulaire de connexion
   */
  function detectLoginForm() {
    // Rechercher les champs de mot de passe
    const passwordFields = document.querySelectorAll('input[type="password"]');
    
    if (passwordFields.length === 0) {
      return null;
    }
    
    // Pour chaque champ de mot de passe, trouver le champ username associé
    passwordFields.forEach(passwordField => {
      const form = passwordField.closest('form') || document;
      
      // Chercher un champ username/email dans le même formulaire
      const usernameField = form.querySelector(
        'input[type="text"], input[type="email"], input[name*="user"], input[name*="email"], input[name*="login"], input[id*="user"], input[id*="email"], input[id*="login"]'
      );
      
      if (usernameField && passwordField) {
        formData.usernameField = usernameField;
        formData.passwordField = passwordField;
        formData.form = passwordField.closest('form');
        
        console.log("Formulaire de connexion détecté:", {
          username: usernameField.name || usernameField.id,
          password: passwordField.name || passwordField.id
        });
        
        // Ajouter des boutons d'auto-fill
        addAutoFillButton(usernameField, passwordField);
      }
    });
  }
  
  /**
   * Ajoute un bouton d'auto-fill près des champs
   */
  function addAutoFillButton(usernameField, passwordField) {
    // Vérifier si le bouton n'existe pas déjà
    if (passwordField.parentElement.querySelector('.pm-autofill-btn')) {
      return;
    }
    
    // Créer le bouton
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'pm-autofill-btn';
    button.textContent = '🔑';
    button.title = 'Remplir avec Password Manager';
    button.style.cssText = `
      position: absolute;
      right: 5px;
      top: 50%;
      transform: translateY(-50%);
      border: 1px solid #ccc;
      background: white;
      border-radius: 3px;
      cursor: pointer;
      padding: 2px 8px;
      font-size: 16px;
      z-index: 10000;
      transition: background 0.2s;
    `;
    
    button.addEventListener('mouseenter', () => {
      button.style.background = '#f0f0f0';
    });
    
    button.addEventListener('mouseleave', () => {
      button.style.background = 'white';
    });
    
    button.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      showCredentialsMenu(usernameField, passwordField);
    });
    
    // Positionner le parent en relative si nécessaire
    const parent = passwordField.parentElement;
    if (getComputedStyle(parent).position === 'static') {
      parent.style.position = 'relative';
    }
    
    parent.appendChild(button);
  }
  
  /**
   * Affiche le menu de sélection des identifiants
   */
  function showCredentialsMenu(usernameField, passwordField) {
    const url = window.location.href;
    
    // Demander les credentials au background script
    browser.runtime.sendMessage({
      type: "searchCredentials",
      url: url
    }).then(response => {
      if (response.status === "success" && response.credentials) {
        displayCredentialsPopup(response.credentials, usernameField, passwordField);
      } else {
        showNotification("Aucun identifiant trouvé pour ce site", "info");
      }
    }).catch(error => {
      console.error("Erreur lors de la recherche:", error);
      showNotification("Erreur de connexion au gestionnaire", "error");
    });
  }
  
  /**
   * Affiche un popup avec la liste des identifiants
   */
  function displayCredentialsPopup(credentials, usernameField, passwordField) {
    // Supprimer l'ancien popup s'il existe
    const oldPopup = document.querySelector('.pm-credentials-popup');
    if (oldPopup) {
      oldPopup.remove();
    }
    
    // Créer le popup
    const popup = document.createElement('div');
    popup.className = 'pm-credentials-popup';
    popup.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: white;
      border: 1px solid #ccc;
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      z-index: 100000;
      padding: 20px;
      min-width: 300px;
      max-width: 400px;
      max-height: 400px;
      overflow-y: auto;
    `;
    
    // Titre
    const title = document.createElement('h3');
    title.textContent = 'Sélectionner un identifiant';
    title.style.cssText = 'margin: 0 0 15px 0; font-size: 16px;';
    popup.appendChild(title);
    
    // Liste des credentials
    if (credentials.length === 0) {
      const noResult = document.createElement('p');
      noResult.textContent = 'Aucun identifiant trouvé pour ce site';
      noResult.style.color = '#666';
      popup.appendChild(noResult);
    } else {
      credentials.forEach(cred => {
        const item = document.createElement('div');
        item.style.cssText = `
          padding: 10px;
          margin: 5px 0;
          border: 1px solid #ddd;
          border-radius: 4px;
          cursor: pointer;
          transition: background 0.2s;
        `;
        
        item.innerHTML = `
          <div style="font-weight: bold;">${escapeHtml(cred.title || cred.url)}</div>
          <div style="color: #666; font-size: 14px;">${escapeHtml(cred.username)}</div>
        `;
        
        item.addEventListener('mouseenter', () => {
          item.style.background = '#f0f0f0';
        });
        
        item.addEventListener('mouseleave', () => {
          item.style.background = 'white';
        });
        
        item.addEventListener('click', () => {
          fillCredentials(cred, usernameField, passwordField);
          popup.remove();
        });
        
        popup.appendChild(item);
      });
    }
    
    // Bouton fermer
    const closeBtn = document.createElement('button');
    closeBtn.textContent = 'Fermer';
    closeBtn.style.cssText = `
      margin-top: 15px;
      padding: 8px 16px;
      border: 1px solid #ccc;
      background: #f5f5f5;
      border-radius: 4px;
      cursor: pointer;
      width: 100%;
    `;
    closeBtn.addEventListener('click', () => popup.remove());
    popup.appendChild(closeBtn);
    
    // Overlay
    const overlay = document.createElement('div');
    overlay.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0,0,0,0.5);
      z-index: 99999;
    `;
    overlay.addEventListener('click', () => {
      popup.remove();
      overlay.remove();
    });
    
    document.body.appendChild(overlay);
    document.body.appendChild(popup);
  }
  
  /**
   * Remplit les champs avec les credentials
   */
  function fillCredentials(cred, usernameField, passwordField) {
    // Demander le mot de passe complet au native host
    browser.runtime.sendMessage({
      type: "getCredentials",
      entryId: cred.id
    }).then(response => {
      if (response.status === "success") {
        usernameField.value = response.username;
        passwordField.value = response.password;
        
        // Déclencher les événements pour que les frameworks JS détectent le changement
        ['input', 'change'].forEach(eventType => {
          usernameField.dispatchEvent(new Event(eventType, { bubbles: true }));
          passwordField.dispatchEvent(new Event(eventType, { bubbles: true }));
        });
        
        showNotification("Identifiants remplis avec succès", "success");
      } else {
        showNotification("Erreur lors de la récupération du mot de passe", "error");
      }
    }).catch(error => {
      console.error("Erreur:", error);
      showNotification("Erreur de connexion", "error");
    });
  }
  
  /**
   * Affiche une notification temporaire
   */
  function showNotification(message, type = "info") {
    const notification = document.createElement('div');
    notification.textContent = message;
    notification.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      background: ${type === 'success' ? '#4CAF50' : type === 'error' ? '#f44336' : '#2196F3'};
      color: white;
      padding: 15px 20px;
      border-radius: 4px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
      z-index: 100001;
      font-size: 14px;
      animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
      notification.style.opacity = '0';
      notification.style.transition = 'opacity 0.3s';
      setTimeout(() => notification.remove(), 300);
    }, 3000);
  }
  
  /**
   * Échappe le HTML
   */
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
  
  /**
   * Détecte la soumission de formulaire pour proposer de sauvegarder
   */
  function setupFormSubmitListener() {
    document.addEventListener('submit', (e) => {
      if (formData.usernameField && formData.passwordField) {
        const username = formData.usernameField.value;
        const password = formData.passwordField.value;
        
        if (username && password) {
          // Proposer de sauvegarder après un délai (pour laisser la connexion se faire)
          setTimeout(() => {
            offerToSaveCredentials(username, password);
          }, 1000);
        }
      }
    }, true);
  }
  
  /**
   * Propose de sauvegarder les identifiants
   */
  function offerToSaveCredentials(username, password) {
    // Vérifier si ces credentials existent déjà
    browser.runtime.sendMessage({
      type: "searchCredentials",
      url: window.location.href
    }).then(response => {
      if (response.status === "success") {
        const exists = response.credentials.some(c => c.username === username);
        
        if (!exists) {
          showSavePrompt(username, password);
        }
      }
    });
  }
  
  /**
   * Affiche une invite pour sauvegarder
   */
  function showSavePrompt(username, password) {
    const prompt = document.createElement('div');
    prompt.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      background: white;
      border: 1px solid #ccc;
      border-radius: 8px;
      padding: 20px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      z-index: 100000;
      min-width: 300px;
    `;
    
    prompt.innerHTML = `
      <h4 style="margin: 0 0 10px 0;">Sauvegarder ce mot de passe ?</h4>
      <p style="margin: 0 0 15px 0; color: #666; font-size: 14px;">
        Pour ${escapeHtml(window.location.hostname)}
      </p>
      <div style="display: flex; gap: 10px;">
        <button id="pm-save-yes" style="flex: 1; padding: 8px; background: #2196F3; color: white; border: none; border-radius: 4px; cursor: pointer;">
          Sauvegarder
        </button>
        <button id="pm-save-no" style="flex: 1; padding: 8px; background: #ccc; border: none; border-radius: 4px; cursor: pointer;">
          Non
        </button>
      </div>
    `;
    
    document.body.appendChild(prompt);
    
    document.getElementById('pm-save-yes').addEventListener('click', () => {
      browser.runtime.sendMessage({
        type: "saveCredentials",
        url: window.location.href,
        username: username,
        password: password,
        title: document.title || window.location.hostname
      }).then(() => {
        showNotification("Identifiants sauvegardés", "success");
        prompt.remove();
      });
    });
    
    document.getElementById('pm-save-no').addEventListener('click', () => {
      prompt.remove();
    });
    
    // Auto-close après 10 secondes
    setTimeout(() => {
      if (document.body.contains(prompt)) {
        prompt.remove();
      }
    }, 10000);
  }
  
  // Initialisation
  function init() {
    // Détecter les formulaires au chargement
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', detectLoginForm);
    } else {
      detectLoginForm();
    }
    
    // Observer les changements du DOM pour les SPAs
    const observer = new MutationObserver((mutations) => {
      detectLoginForm();
    });
    
    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
    
    // Écouter les soumissions de formulaires
    setupFormSubmitListener();
  }
  
  init();
  
})();
