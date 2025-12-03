/**
 * Background Script pour l'extension Password Manager
 * Gère la communication avec le Native Messaging Host
 */

// Définir le badge DEV au démarrage
browser.browserAction.setBadgeText({ text: "DEV" });
browser.browserAction.setBadgeBackgroundColor({ color: "#ff9800" });

// Connexion au native messaging host
let nativePort = null;
let isConnected = false;

/**
 * Initialise la connexion au native host
 */
function connectNativeHost() {
  try {
    nativePort = browser.runtime.connectNative("com.passwordmanager.native.dev");
    
    nativePort.onMessage.addListener((message) => {
      console.log("Message reçu du native host:", message);
      handleNativeMessage(message);
    });
    
    nativePort.onDisconnect.addListener(() => {
      console.error("Déconnexion du native host:", browser.runtime.lastError);
      isConnected = false;
      nativePort = null;
      
      // Tentative de reconnexion après 5 secondes
      setTimeout(connectNativeHost, 5000);
    });
    
    isConnected = true;
    console.log("Connecté au native host");
    
    // Test de connexion
    sendToNativeHost({ action: "ping" });
    
  } catch (error) {
    console.error("Erreur de connexion au native host:", error);
    isConnected = false;
  }
}

/**
 * Envoie un message au native host
 */
let pendingRequests = new Map();

function sendToNativeHost(message) {
  if (!isConnected || !nativePort) {
    console.error("Pas de connexion au native host");
    return Promise.reject(new Error("Not connected to native host"));
  }
  
  return new Promise((resolve, reject) => {
    const messageId = Date.now() + Math.random();
    message.messageId = messageId;
    
    // Stocker la requête en attente
    pendingRequests.set(message.action, { resolve, reject, messageId });
    
    // Timeout après 10 secondes
    const timeout = setTimeout(() => {
      pendingRequests.delete(message.action);
      reject(new Error("Timeout waiting for response"));
    }, 10000);
    
    // Stocker aussi le timeout pour le nettoyer
    pendingRequests.get(message.action).timeout = timeout;
    
    console.log("Envoi au native host:", message);
    nativePort.postMessage(message);
  });
}

/**
 * Gère les messages reçus du native host
 */
function handleNativeMessage(message) {
  console.log("Réponse du native host:", message);
  
  // Mapper les actions de réponse aux actions originales
  const actionMap = {
    'pong': 'ping',
    'status_response': 'check_status',
    'search_response': 'search_credentials',
    'get_response': 'get_credentials',
    'save_response': 'save_credentials',
    'generate_response': 'generate_password'
  };
  
  const originalAction = actionMap[message.action] || message.action;
  
  // Résoudre la promesse en attente
  if (pendingRequests.has(originalAction)) {
    const pending = pendingRequests.get(originalAction);
    clearTimeout(pending.timeout);
    pending.resolve(message);
    pendingRequests.delete(originalAction);
  }
  
  // Diffuser aussi aux content scripts si nécessaire
  browser.tabs.query({active: true, currentWindow: true}).then(tabs => {
    if (tabs[0]) {
      browser.tabs.sendMessage(tabs[0].id, {
        type: "nativeResponse",
        data: message
      }).catch(err => console.log("Tab not ready for messages"));
    }
  });
}

/**
 * Gère les messages des content scripts
 */
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("Message reçu:", message);
  
  switch (message.type) {
    case "searchCredentials":
      sendToNativeHost({
        action: "search_credentials",
        url: message.url
      })
      .then(response => sendResponse(response))
      .catch(error => sendResponse({ status: "error", error: error.message }));
      return true; // Indique une réponse asynchrone
      
    case "getCredentials":
      sendToNativeHost({
        action: "get_credentials",
        entry_id: message.entryId
      })
      .then(response => sendResponse(response))
      .catch(error => sendResponse({ status: "error", error: error.message }));
      return true;
      
    case "saveCredentials":
      sendToNativeHost({
        action: "save_credentials",
        url: message.url,
        username: message.username,
        password: message.password,
        title: message.title
      })
      .then(response => sendResponse(response))
      .catch(error => sendResponse({ status: "error", error: error.message }));
      return true;
      
    case "generatePassword":
      sendToNativeHost({
        action: "generate_password",
        length: message.length || 20
      })
      .then(response => sendResponse(response))
      .catch(error => sendResponse({ status: "error", error: error.message }));
      return true;
      
    case "checkStatus":
      sendToNativeHost({
        action: "check_status"
      })
      .then(response => sendResponse(response))
      .catch(error => sendResponse({ status: "error", error: error.message }));
      return true;
      
    default:
      console.warn("Type de message inconnu:", message.type);
      sendResponse({ status: "error", error: "Unknown message type" });
  }
});

/**
 * Gère les clics sur l'icône de l'extension
 */
browser.browserAction.onClicked.addListener((tab) => {
  // Le popup s'ouvrira automatiquement grâce à default_popup dans manifest.json
  console.log("Extension icon clicked");
});

// Initialisation au démarrage
connectNativeHost();

// Ping régulier pour maintenir la connexion
setInterval(() => {
  if (isConnected) {
    sendToNativeHost({ action: "ping" }).catch(err => {
      console.error("Ping failed:", err);
    });
  }
}, 30000); // Toutes les 30 secondes

console.log("Background script initialisé");
