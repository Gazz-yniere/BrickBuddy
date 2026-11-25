/* Couche commune : popin de confirmation, messages, roue de chargement et
   mise à jour des pages sans rechargement. Les fichiers js/* s'appuient sur elle. */

function showInteractionError(message) {
  const container = document.querySelector("#interaction-messages");
  if (!container) {
    return;
  }
  container.replaceChildren();
  const flash = document.createElement("div");
  flash.className = "flash error";
  flash.textContent = message;
  container.append(flash);
  container.hidden = false;
}

// Roue de chargement : le bouton reste en place, rien ne bouge pendant l'attente.
function startLoading(control) {
  if (!(control instanceof HTMLElement) || control.classList.contains("is-loading")) {
    return;
  }
  control.classList.add("is-loading");
  control.setAttribute("aria-busy", "true");
  if (!control.querySelector(".button-spinner")) {
    const spinner = document.createElement("span");
    spinner.className = "button-spinner";
    spinner.setAttribute("aria-hidden", "true");
    control.prepend(spinner);
  }
}

function stopLoading(control) {
  if (!(control instanceof HTMLElement)) {
    return;
  }
  control.classList.remove("is-loading");
  control.removeAttribute("aria-busy");
  control.querySelector(".button-spinner")?.remove();
}

window.addEventListener("pageshow", () => {
  document.querySelectorAll(".is-loading").forEach(stopLoading);
});

// Les panneaux dépliables gardent leur état d'ouverture quand la page est
// remplacée sans rechargement : une ligne ouverte ne se referme pas au clic.
function detailsKey(details) {
  if (details.hasAttribute("data-group-key")) {
    return JSON.stringify(["couleur", details.dataset.groupKey]);
  }
  if (details.hasAttribute("data-minifig-set")) {
    return JSON.stringify(["figurine", details.dataset.minifigSet, details.dataset.minifigFig]);
  }
  return null;
}

function rememberDetails(root) {
  const opened = new Map();
  root.querySelectorAll("details").forEach((details) => {
    const key = detailsKey(details);
    if (key !== null) {
      opened.set(key, details.open);
    }
  });
  return opened;
}

function restoreDetails(root, opened) {
  root.querySelectorAll("details").forEach((details) => {
    const key = detailsKey(details);
    if (key !== null && opened.has(key)) {
      details.open = opened.get(key);
    }
  });
}

// La popin est partagée : chaque formulaire précise son titre et son libellé
// d'action, pour ne jamais proposer « Retirer le set » sur une notice.
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (
    !(form instanceof HTMLFormElement) ||
    !form.matches("[data-confirm]") ||
    form.dataset.confirmed === "true"
  ) {
    return;
  }

  const dialog = document.querySelector("#confirm-dialog");
  if (!(dialog instanceof HTMLDialogElement)) {
    return;
  }

  event.preventDefault();
  const title = dialog.querySelector("[data-confirm-title]");
  if (title) {
    title.textContent = form.dataset.confirmTitle || "Confirmer le retrait";
  }
  const confirmButton = dialog.querySelector("[data-confirm-button]");
  if (confirmButton) {
    confirmButton.textContent = form.dataset.confirmButton || "Retirer le set";
  }
  dialog.querySelector("[data-confirm-message]").textContent =
    form.dataset.confirmMessage || "Confirmer cette action ?";
  dialog.addEventListener(
    "close",
    () => {
      if (dialog.returnValue !== "confirm") {
        return;
      }
      // Le retrait d'une notice se traite sans recharger la page : le carrousel
      // garde la liste complète des livres trouvés.
      document.dispatchEvent(new CustomEvent("action-confirme", { detail: { form } }));
      if (form.matches(".instruction-delete-form")) {
        return;
      }
      form.dataset.confirmed = "true";
      form.requestSubmit();
    },
    { once: true },
  );
  dialog.showModal();
});

/* Mise à jour sans rechargement : par défaut, toute écriture et tout filtre est
   envoyé en fetch, la page réponse remplace la zone de résultats. Le serveur
   garde sa réponse HTML habituelle, aucun protocole nouveau n'est nécessaire.
   Les formulaires qui s'excluent eux-mêmes portent data-static. */
const RESULTS_HOST = "[data-page-results]";

// Les formulaires qui traitent leur propre réponse JSON ne passent pas par ici.
const NATIVE_FORMS =
  ".set-status-form, .minifig-part-status-form, .stock-take-form, .stock-step-form, " +
  ".stock-add-form, .add-stock-form, .instruction-download-form, .instruction-upload";

async function fetchPage(url, body) {
  const response = await fetch(url, {
    method: body ? "POST" : "GET",
    ...(body ? { body } : {}),
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!response.ok) {
    throw new Error("La page n'a pas pu être mise à jour.");
  }
  return response;
}

// La page réponse remplace la zone de résultats : compteurs, filtres, messages
// et navigation suivent, rien ne se recharge.
async function applyPage(response) {
  const host = document.querySelector(RESULTS_HOST);
  if (!host) {
    return false; // page sans zone de résultats (écran de connexion)
  }
  const parsed = new DOMParser().parseFromString(await response.text(), "text/html");
  const fresh = parsed.querySelector(RESULTS_HOST);
  if (!fresh) {
    throw new Error("La page n'a pas pu être mise à jour.");
  }
  const opened = rememberDetails(host);
  host.replaceChildren(...fresh.children);
  restoreDetails(host, opened);
  syncNavigationCounts(parsed);
  syncNavigationActive(parsed);
  syncBreadcrumb(parsed);
  refreshCssIfChanged(parsed);
  document.dispatchEvent(new CustomEvent("page-updated", { detail: { host } }));
  return true;
}

// Une feuille de style qui a changé de contenu change d'empreinte dans la page
// réponse. Le remplacement de la zone de résultats ne touche pas le <head> :
// sans cette relecture, la navigation dynamique garderait l'ancienne feuille.
function refreshCssIfChanged(parsed) {
  document.querySelectorAll("head link[rel='stylesheet']").forEach((link) => {
    const current = link.getAttribute("href");
    const fresh = parsed.querySelector(`head link[rel='stylesheet'][href="${current}"]`);
    if (fresh && fresh.getAttribute("href") !== current) {
      link.setAttribute("href", fresh.getAttribute("href"));
    }
  });
}

async function updatePageFrom(form) {
  const target = new URL(form.action, window.location.href);
  const body = new FormData(form);
  const filtering = form.method.toLowerCase() === "get";
  if (filtering) {
    target.search = new URLSearchParams(body).toString();
  }
  const response = await fetchPage(target.toString(), filtering ? null : body);
  if (!(await applyPage(response))) {
    return false;
  }
  replaceLocation(response.url);
  return true;
}

function replaceLocation(url) {
  try {
    window.history.replaceState(window.history.state, "", url);
  } catch {
    // Contexte de navigation particulier : le libellé de l'URL n'est pas indispensable.
  }
}

function syncNavigationCounts(parsed) {
  document.querySelectorAll("[data-nav-count]").forEach((badge) => {
    const fresh = parsed.querySelector(`[data-nav-count="${badge.dataset.navCount}"]`);
    if (fresh) {
      badge.textContent = fresh.textContent;
    }
  });
}

// Un formulaire qui redirige vers une autre page change aussi l'onglet actif.
function syncNavigationActive(parsed) {
  const fresh = parsed.querySelector(".nav-link.active");
  if (!fresh) {
    return;
  }
  document.querySelectorAll(".nav-link").forEach((link) => {
    link.classList.toggle("active", link.href === fresh.href);
  });
}

function syncBreadcrumb(parsed) {
  const fresh = parsed.querySelector("[data-page-title]");
  const current = document.querySelector("[data-page-title]");
  if (fresh && current) {
    current.textContent = fresh.textContent;
  }
}

// Une action traitée en JSON ne renvoie que la carte concernée : les compteurs
// de la page reprennent la valeur réelle en redemandant la page, sans rechargement.
async function refreshCurrentPage() {
  try {
    await applyPage(await fetchPage(window.location.href, null));
  } catch {
    // L'action est bien passée : la page garde ce qu'elle affiche.
  }
}

// Les relèves (prix, taux) tournent en arrière-plan ; la page ne se recharge
// pas d'elle-même : le badge « en cours » se met à jour à la prochaine navigation.

document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (
    !(form instanceof HTMLFormElement) ||
    form.matches(NATIVE_FORMS) ||
    form.matches("[data-static]") ||
    // Le formulaire de la popin close le <dialog> lui-même : ce n'est pas une
    // action sur la page, et son action par défaut est la page courante.
    form.matches("[method=\"dialog\"]") ||
    form.enctype === "multipart/form-data" ||
    (form.matches("[data-confirm]") && form.dataset.confirmed !== "true") ||
    form.dataset.pending
  ) {
    return; // upload, popin, déconnexion et formulaires JSON : leur propre comportement
  }
  if (!document.querySelector(RESULTS_HOST)) {
    return; // écran de connexion : navigation normale
  }
  // Un filtre comme une écriture : la réponse remplace la page, jamais un rechargement.
  event.preventDefault();
  const trigger =
    event.submitter instanceof HTMLElement ? event.submitter : form.querySelector("button");
  form.dataset.pending = "true";
  startLoading(trigger);
  try {
    await updatePageFrom(form);
  } catch (error) {
    showInteractionError(
      error instanceof Error ? error.message : "La page n'a pas pu être mise à jour.",
    );
  } finally {
    delete form.dataset.pending;
    stopLoading(trigger);
  }
});

// Les chips et les liens de filtre sont des liens : ils sont envoyés de la
// même façon, sans recharger la page.
document.addEventListener("click", async (event) => {
  if (!(event.target instanceof Element)) {
    return;
  }
  const link = event.target.closest("a[data-dynamic]");
  if (!(link instanceof HTMLAnchorElement) || !document.querySelector(RESULTS_HOST)) {
    return;
  }
  event.preventDefault();
  if (link.classList.contains("is-loading")) {
    return;
  }
  startLoading(link);
  try {
    const response = await fetchPage(link.href, null);
    await applyPage(response);
    replaceLocation(response.url);
  } catch (error) {
    showInteractionError(
      error instanceof Error ? error.message : "La page n'a pas pu être mise à jour.",
    );
  } finally {
    stopLoading(link);
  }
});
