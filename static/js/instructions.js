/* Notices : recherche LEGO, carrousel, lecteur PDF, téléchargement, ajout manuel. */

const instructionSearchRoot = document.querySelector("[data-instruction-search]");
const instructionHeadHost = document.querySelector("[data-instruction-head]");
const instructionCarousel = document.querySelector("[data-instruction-carousel]");
let instructionSearchInFlight = false;

function instructionCarouselTrack() {
  return instructionCarousel?.querySelector("[data-carousel-track]") ?? null;
}

function instructionCards() {
  return [...(instructionCarouselTrack()?.querySelectorAll("[data-instruction-card]") ?? [])];
}

// Seules les notices enregistrees se parcourent avec les fleches : une
// proposition LEGO n'a pas encore de fichier a lire.
function readableInstructionCards() {
  return instructionCards().filter((card) => card.dataset.noticeUrl);
}

function cleanInstructionSearchUrl() {
  const target = new URL(window.location.href);
  if (!target.searchParams.has("rechercher") && !target.searchParams.has("construire")) {
    return;
  }
  target.searchParams.delete("rechercher");
  target.searchParams.delete("construire");
  window.history.replaceState(window.history.state, "", target.toString());
}

// Fleches du carrousel : elles suivent le nombre de notices lisibles et
// designent toujours la voisine, en faisant le tour de la liste.
function refreshInstructionCarousel() {
  const cards = readableInstructionCards();
  const selected = Math.max(
    cards.findIndex((card) => card.classList.contains("is-current")),
    0,
  );
  const multi = cards.length > 1;
  [
    instructionCarousel?.querySelector("[data-carousel-arrow='previous']"),
    instructionCarousel?.querySelector("[data-carousel-arrow='next']"),
  ].forEach((arrow, side) => {
    if (!(arrow instanceof HTMLAnchorElement)) {
      return;
    }
    arrow.hidden = !multi;
    if (!multi) {
      arrow.removeAttribute("href");
      return;
    }
    const neighbour = cards[(selected + (side === 0 ? -1 : 1) + cards.length) % cards.length];
    arrow.href = neighbour.dataset.noticeUrl;
  });
}

// La recherche renvoie l'en-tete du panneau et les tuiles des notices qui
// restent a telecharger : les tuiles entrent dans le carrousel, a la suite des
// notices deja enregistrees.
function applyInstructionResults(html) {
  const parsed = new DOMParser().parseFromString(html, "text/html");
  const head = parsed.querySelector("[data-results-head]");
  if (head && instructionHeadHost) {
    instructionHeadHost.innerHTML = head.innerHTML;
  }
  const track = instructionCarouselTrack();
  parsed.querySelectorAll("[data-results-tiles] [data-download-tile]").forEach((tile) => {
    track?.append(document.importNode(tile, true));
  });
  refreshInstructionCarousel();
}

async function runInstructionSearch(link) {
  if (!instructionSearchRoot || !instructionHeadHost || instructionSearchInFlight) {
    return;
  }
  const searchUrl = instructionSearchRoot.dataset.searchUrl;
  if (!searchUrl) {
    return;
  }
  const status = document.querySelector("[data-search-status]");
  const trigger = link || instructionSearchRoot.querySelector("[data-search-instructions]");
  instructionSearchInFlight = true;
  startLoading(trigger);
  instructionSearchRoot.setAttribute("aria-busy", "true");
  if (status) {
    status.textContent = "Recherche des notices officielles en cours…";
  }
  try {
    const response = await fetch(searchUrl, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    if (!response.ok) {
      throw new Error("Recherche impossible.");
    }
    applyInstructionResults(await response.text());
    if (status) {
      status.textContent = "";
    }
    cleanInstructionSearchUrl();
  } catch {
    if (status) {
      status.textContent = "Recherche impossible. Réessaie dans un instant.";
    }
  } finally {
    instructionSearchInFlight = false;
    instructionSearchRoot.removeAttribute("aria-busy");
    stopLoading(trigger);
  }
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-search-instructions]");
  if (!(link instanceof HTMLAnchorElement)) {
    // « Construire » navigue immédiatement, sans roue de chargement.
    return;
  }
  if (link.classList.contains("is-loading")) {
    event.preventDefault();
    return;
  }
  event.preventDefault();
  startLoading(link);
  const status = document.querySelector("[data-search-status]");
  if (status) {
    status.textContent = "Recherche des notices officielles en cours…";
  }
  runInstructionSearch(link);
});

function autoSearchInstructions() {
  if (instructionSearchRoot?.dataset.autoSearch !== "1") {
    cleanInstructionSearchUrl();
    return;
  }
  window.requestAnimationFrame(() => {
    runInstructionSearch(instructionSearchRoot.querySelector("[data-search-instructions]"));
  });
}

window.addEventListener("load", autoSearchInstructions, { once: true });

window.addEventListener("pageshow", (event) => {
  if (!event.persisted) {
    return;
  }
  instructionSearchInFlight = false;
  instructionSearchRoot?.removeAttribute("aria-busy");
});

// Le livre lu est place a une largeur et demie du bord gauche du carrousel : les
// livres precedents restent dans le champ, le premier est colle a gauche. Le
// placement est borne pour que le livre lu tienne toujours entier dans le
// carrousel, sans jamais laisser de vide apres lui.
function placeInstructionCard(card) {
  const track = instructionCarouselTrack();
  if (!(track instanceof HTMLElement) || !(card instanceof HTMLElement)) {
    return;
  }
  const gap = Number.parseFloat(getComputedStyle(track).columnGap) || 12;
  const lead = card.offsetWidth + gap;
  const cardLeft =
    card.getBoundingClientRect().left - track.getBoundingClientRect().left + track.scrollLeft;
  const view = track.clientWidth;
  const desired = cardLeft - 1.5 * lead;
  const lowest = Math.max(cardLeft + card.offsetWidth - view, 0);
  const highest = Math.max(Math.min(cardLeft, track.scrollWidth - view), 0);
  track.scrollLeft = Math.min(Math.max(desired, lowest), highest);
}

function markViewerLoaded(shell) {
  if (shell instanceof HTMLElement) {
    shell.classList.add("is-loaded");
  }
}

function viewerIsPainted(viewer) {
  try {
    // Cadre de meme origine : le lecteur PDF apparait des qu'une notice est
    // lisible, sans recharger la page (la page vide « about:blank » reste a zero element).
    return (viewer.contentDocument?.body?.childElementCount ?? 0) > 0;
  } catch {
    return false;
  }
}

const viewerWatches = new WeakMap();

// Le bandeau « Chargement de la notice… » ne doit jamais rester en place.
// L'evenement « load » du cadre est le signal fiable (le lecteur PDF natif de
// Chrome ne laisse pas lire son contenu) : des qu'il arrive, le bandeau se
// leve. La surveillance periodique reste en secours pour les navigateurs qui
// ne declenchent pas cet evenement.
function watchViewer(shell, viewer) {
  window.clearInterval(viewerWatches.get(shell));
  let attempts = 0;
  const timer = window.setInterval(() => {
    attempts += 1;
    if (viewerIsPainted(viewer) || attempts >= 60) {
      window.clearInterval(timer);
      viewerWatches.delete(shell);
      markViewerLoaded(shell);
    }
  }, 200);
  viewerWatches.set(shell, timer);
}

document.querySelectorAll("[data-pdf-viewer]").forEach((shell) => {
  const viewer = shell.querySelector("iframe");
  if (!(viewer instanceof HTMLIFrameElement)) {
    return;
  }
  viewer.addEventListener("load", () => {
    window.clearInterval(viewerWatches.get(shell));
    viewerWatches.delete(shell);
    markViewerLoaded(shell);
  });
  watchViewer(shell, viewer);
});

function showInstructionPdf(card) {
  const band = document.querySelector(".instruction-viewer-band");
  const shell = document.querySelector("[data-pdf-viewer]");
  const viewer = shell?.querySelector("iframe.instruction-viewer");
  const pdfUrl = card.dataset.pdfUrl;
  if (!(viewer instanceof HTMLIFrameElement) || !pdfUrl) {
    return;
  }
  band?.classList.remove("is-hidden");
  // La notice est deja dans le lecteur : rien a recharger.
  if (viewer.src.split("#")[0].endsWith(pdfUrl)) {
    return;
  }
  shell.classList.remove("is-loaded");
  viewer.src = `${pdfUrl}#page=1&view=FitH&navpanes=0`;
  viewer.title = `Notice ${card.querySelector(".instruction-card-file")?.textContent ?? ""}`;
  watchViewer(shell, viewer);
}

function hideInstructionViewer() {
  const band = document.querySelector(".instruction-viewer-band");
  const shell = document.querySelector("[data-pdf-viewer]");
  const viewer = shell?.querySelector("iframe.instruction-viewer");
  band?.classList.add("is-hidden");
  shell?.classList.remove("is-loaded");
  if (viewer instanceof HTMLIFrameElement) {
    window.clearInterval(viewerWatches.get(shell));
    viewerWatches.delete(shell);
    viewer.removeAttribute("src");
    viewer.title = "";
  }
  try {
    const target = new URL(window.location.href);
    ["notice", "construire", "rechercher"].forEach((key) => target.searchParams.delete(key));
    window.history.replaceState(window.history.state, "", target.toString());
  } catch {
    // Contexte de navigation particulier : l'URL n'est pas indispensable.
  }
}

// Notices immuables : l'URL d'une notice designe toujours le meme fichier, le
// navigateur la garde donc sans revalidation. On precharge le livre affiche et
// ses deux voisins pour que changer de notice se fasse sans attente. Un gros
// PDF n'est pas precharge : on ne telecharge pas 200 Mo pendant que la page
// est au repos, le lecteur le chargera au clic.
const PREFETCH_LIMIT_BYTES = 25 * 1024 * 1024;
const prefetchedPdfs = new Set();

function prefetchInstructionCard(card) {
  if (!(card instanceof HTMLElement)) {
    return;
  }
  const url = card.dataset.pdfUrl;
  const size = Number(card.dataset.pdfSize);
  if (!url || prefetchedPdfs.has(url) || (size && size > PREFETCH_LIMIT_BYTES)) {
    return;
  }
  prefetchedPdfs.add(url);
  const idle = window.requestIdleCallback
    || ((callback) => window.setTimeout(callback, 250));
  idle(() => {
    fetch(url, { cache: "force-cache", credentials: "same-origin" }).catch(() => {
      // Prechargement impossible (notice supprimee, reseau) : le lecteur
      // chargera la notice au moment ou on la choisit.
      prefetchedPdfs.delete(url);
    });
  });
}

function prefetchInstructionNeighbours(card) {
  const cards = instructionCards();
  const index = cards.indexOf(card);
  if (index === -1 || cards.length < 2) {
    return;
  }
  prefetchInstructionCard(cards[(index + 1) % cards.length]);
  prefetchInstructionCard(cards[(index - 1 + cards.length) % cards.length]);
}

function selectInstructionCard(card) {
  const cards = instructionCards();
  const index = cards.indexOf(card);
  if (index === -1) {
    return;
  }
  cards.forEach((other, position) => {
    const current = position === index;
    other.classList.toggle("is-current", current);
    if (current) {
      other.setAttribute("aria-current", "true");
    } else {
      other.removeAttribute("aria-current");
    }
    const badge = other.querySelector("[data-current-badge]");
    if (badge) {
      badge.hidden = !current;
    }
  });
  showInstructionPdf(card);
  placeInstructionCard(card);
  prefetchInstructionNeighbours(card);
  refreshInstructionCarousel();
  try {
    window.history.replaceState(window.history.state, "", card.dataset.noticeUrl);
  } catch {
    // Contexte de navigation particulier (page locale, iframe cloisonne) :
    // le libelle de l'URL n'est pas indispensable, la notice est deja changee.
  }
}

document.addEventListener("click", (event) => {
  if (!(instructionCarousel instanceof HTMLElement)) {
    return;
  }
  const arrow = event.target.closest("[data-carousel-arrow]");
  if (arrow instanceof HTMLAnchorElement) {
    const card = readableInstructionCards().find(
      (item) => item.dataset.noticeUrl === arrow.getAttribute("href"),
    );
    if (!card) {
      return;
    }
    event.preventDefault();
    selectInstructionCard(card);
    return;
  }
  const card = event.target.closest("[data-instruction-card]");
  if (!(card instanceof HTMLElement)) {
    return;
  }
  // « Ouvrir » et « Supprimer » gardent leur propre comportement.
  if (event.target.closest(".instruction-card-actions a, .instruction-card-actions button")) {
    return;
  }
  // Le clic sert a choisir le livre ; une selection de texte garde sa liberté.
  if (window.getSelection()?.toString()) {
    return;
  }
  event.preventDefault();
  // Une proposition LEGO se telecharge au clic sur la tuile.
  if (card.hasAttribute("data-download-tile")) {
    const form = card.querySelector(".instruction-download-form");
    if (form instanceof HTMLFormElement && !form.classList.contains("is-loading")) {
      downloadInstructionForm(form);
    }
    return;
  }
  selectInstructionCard(card);
});

instructionCarouselTrack()?.addEventListener("keydown", (event) => {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
    return;
  }
  const cards = readableInstructionCards();
  if (cards.length < 2) {
    return;
  }
  const selected = cards.findIndex((card) => card.classList.contains("is-current"));
  const shift = event.key === "ArrowRight" ? 1 : -1;
  event.preventDefault();
  selectInstructionCard(cards[(Math.max(selected, 0) + shift + cards.length) % cards.length]);
});

instructionCarousel?.addEventListener("pointerover", (event) => {
  prefetchInstructionCard(event.target.closest("[data-instruction-card]"));
});

window.addEventListener("load", () => {
  const current = instructionCards().find((card) => card.classList.contains("is-current"));
  if (current) {
    placeInstructionCard(current);
    prefetchInstructionCard(current);
    prefetchInstructionNeighbours(current);
  }
  refreshInstructionCarousel();
}, { once: true });

function instructionDownloadStatus(message) {
  const status = document.querySelector("[data-download-status]");
  if (status) {
    status.textContent = message;
  }
}

// Le panneau n'a plus qu'un compte rendu : on le recalcule a chaque notice
// enregistree, le bouton « Tout télécharger » disparait des qu'il reste moins
// de deux notices a telecharger.
function refreshInstructionHead() {
  const saved = readableInstructionCards().length;
  const pending = document.querySelectorAll("[data-download-tile]").length;
  const count = document.querySelector("[data-instruction-count]");
  if (count) {
    const parts = [];
    if (saved) {
      parts.push(`${saved} notice${saved > 1 ? "s" : ""} enregistrée${saved > 1 ? "s" : ""}`);
    }
    if (pending) {
      parts.push(`${pending} à télécharger`);
    }
    count.textContent = parts.join(" · ");
  }
  const all = document.querySelector("[data-download-all]");
  if (all && pending < 2) {
    all.remove();
  } else if (!all && pending > 1) {
    // Le bouton de telechargement groupé apparait des qu'il reste au moins deux
    // livres a telecharger, meme quand la liste a change sans rechargement.
    document.querySelector("[data-instruction-head]")?.append(buildDownloadAllButton(pending));
  }
}

function buildDownloadAllButton(count) {
  const button = document.createElement("button");
  button.className = "button button-primary";
  button.type = "button";
  button.setAttribute("data-download-all", "");
  button.innerHTML =
    '<span class="button-spinner" aria-hidden="true"></span>' +
    `<span data-download-label>Tout télécharger (${count})</span>`;
  return button;
}

// Une proposition retrouve sa place dans le carrousel : les livres sont ranges
// dans l'ordre de LEGO, les ajouts manuels restent en fin de liste, exactement
// comme quand la page est rechargee.
function instructionSortKey(element) {
  const position = element.dataset?.position;
  return position === undefined || position === "" ? Infinity : Number(position);
}

function insertInstructionTile(track, html) {
  const tile = document.createRange().createContextualFragment(html).firstElementChild;
  if (!(tile instanceof HTMLElement)) {
    return;
  }
  const position = instructionSortKey(tile);
  const next = [...track.children].find((item) => instructionSortKey(item) > position);
  if (next) {
    next.before(tile);
  } else {
    track.append(tile);
  }
}

// Telechargement d'une notice LEGO : le serveur renvoie la tuile deja rendue de
// la notice enregistree. La proposition est remplacee en place, le lecteur
// affiche le PDF : la page n'est jamais rechargee.
async function downloadInstructionForm(form) {
  const button = form.querySelector("button");
  const tile = form.closest("[data-download-tile]");
  if (button) {
    startLoading(button);
    button.disabled = true;
  }
  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.error || "Le téléchargement a échoué.");
    }
    if (result.html && tile) {
      tile.insertAdjacentHTML("beforebegin", result.html);
      const card = tile.previousElementSibling;
      tile.remove();
      if (card instanceof HTMLElement && card.hasAttribute("data-instruction-card")) {
        selectInstructionCard(card);
      }
    }
    refreshInstructionHead();
    return result;
  } catch (error) {
    if (button) {
      stopLoading(button);
      button.disabled = false;
    }
    instructionDownloadStatus(error.message || "Le téléchargement a échoué.");
    return null;
  }
}

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !form.matches(".instruction-download-form")) {
    return;
  }
  event.preventDefault();
  downloadInstructionForm(form);
});

// Retrait d'une notice : la carte sort du carrousel, le livre redevient une
// proposition telechargeable a sa place, le lecteur bascule sur le livre
// suivant. La page n'est jamais rechargee et la liste des livres trouves chez
// LEGO reste complete.
async function deleteInstructionCard(form) {
  const card = form.closest("[data-instruction-card]");
  const button = form.querySelector("button");
  if (button) {
    button.disabled = true;
  }
  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.error || "La notice n'a pas pu être retirée.");
    }
    const wasCurrent = card?.classList.contains("is-current");
    const track = instructionCarouselTrack();
    if (card) {
      card.remove();
    }
    if (result.tile_html && track) {
      insertInstructionTile(track, result.tile_html);
    }
    const cards = readableInstructionCards();
    if (cards.length === 0) {
      hideInstructionViewer();
    } else if (wasCurrent) {
      selectInstructionCard(cards[0]);
    } else {
      refreshInstructionCarousel();
    }
    refreshInstructionHead();
  } catch (error) {
    if (button) {
      button.disabled = false;
    }
    showInteractionError(
      error instanceof Error ? error.message : "La notice n'a pas pu être retirée.",
    );
  }
}

// La popin est commune : le retrait d'une notice se traite ici, sans rechargement.
document.addEventListener("action-confirme", (event) => {
  const form = event.detail?.form;
  if (form instanceof HTMLFormElement && form.matches(".instruction-delete-form")) {
    deleteInstructionCard(form);
  }
});

async function runDownloadAll(button) {
  const forms = [...document.querySelectorAll("[data-download-tile] .instruction-download-form")];
  if (forms.length === 0) {
    button.remove();
    return;
  }
  const label = button.querySelector("[data-download-label]");
  startLoading(button);
  button.disabled = true;
  let saved = 0;
  for (const [index, form] of forms.entries()) {
    if (!form.isConnected) {
      continue;
    }
    const message = `Téléchargement ${index + 1}/${forms.length}…`;
    instructionDownloadStatus(message);
    if (label) {
      label.textContent = message;
    }
    if (await downloadInstructionForm(form)) {
      saved += 1;
    }
  }
  instructionDownloadStatus(
    saved
      ? `${saved} notice${saved === 1 ? "" : "s"} enregistrée${saved === 1 ? "" : "s"}.`
      : "Aucune notice n'a pu être téléchargée.",
  );
  if (button.isConnected) {
    stopLoading(button);
    button.disabled = false;
  }
  refreshInstructionHead();
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-download-all]");
  if (!(button instanceof HTMLButtonElement)) {
    return;
  }
  event.preventDefault();
  if (button.classList.contains("is-loading")) {
    return;
  }
  await runDownloadAll(button);
});

// Ajout manuel : la zone de depot remplace le champ fichier brut. Un clic
// n'importe ou dans la zone ouvre le selecteur, un PDF lache dessus est
// accepte, et « Ajouter » ne s'active qu'avec un fichier PDF.
const uploadZone = document.querySelector(".instruction-upload");
let resetManualUpload = () => {};
if (uploadZone) {
  const input = uploadZone.querySelector("[data-file-input]");
  const zone = uploadZone.querySelector("[data-dropzone]");
  const hint = uploadZone.querySelector("[data-file-name]");
  const submit = uploadZone.querySelector("button[type='submit']");
  const describeUpload = () => {
    const file = input?.files?.[0];
    const pdf = Boolean(file) && /\.pdf$/i.test(file.name);
    zone?.classList.toggle("has-file", Boolean(file) && pdf);
    zone?.classList.toggle("is-error", Boolean(file) && !pdf);
    if (submit) {
      submit.disabled = !pdf;
    }
    if (!hint) {
      return;
    }
    if (!file) {
      hint.textContent = "Aucun fichier choisi";
    } else if (!pdf) {
      hint.textContent = "Choisis un fichier PDF";
    } else {
      hint.textContent = `${file.name} · ${Math.max(1, Math.round(file.size / 1024))} ko`;
    }
  };
  resetManualUpload = () => {
    if (input) {
      input.value = "";
    }
    describeUpload();
  };
  input?.addEventListener("change", describeUpload);
  zone?.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("is-dragging");
  });
  zone?.addEventListener("dragleave", () => zone.classList.remove("is-dragging"));
  zone?.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("is-dragging");
    if (!input || !event.dataTransfer?.files?.length) {
      return;
    }
    input.files = event.dataTransfer.files;
    describeUpload();
  });
}

// L'ajout manuel entre dans le carrousel sans recharger la page : la liste des
// livres trouves chez LEGO reste affichee, le lecteur bascule sur le PDF ajoute.
async function uploadManualInstruction(form) {
  const button = form.querySelector("button[type='submit']");
  if (button) {
    button.disabled = true;
  }
  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.error || "La notice n'a pas été ajoutée.");
    }
    if (result.html) {
      const track = instructionCarouselTrack();
      track?.insertAdjacentHTML("beforeend", result.html);
      const card = track?.lastElementChild;
      if (card instanceof HTMLElement && card.hasAttribute("data-instruction-card")) {
        selectInstructionCard(card);
      }
    }
    resetManualUpload();
    refreshInstructionHead();
  } catch (error) {
    if (button) {
      button.disabled = false;
    }
    showInteractionError(
      error instanceof Error ? error.message : "La notice n'a pas été ajoutée.",
    );
  }
}

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !form.matches(".instruction-upload")) {
    return;
  }
  event.preventDefault();
  uploadManualInstruction(form);
});
