const app = document.querySelector("#demo-app");
// Inventory facts: https://www.brickowl.com/catalog/lego-millennium-falcon-microfighter-set-75193/inventory
const inventory = [
  ["99781", "Support 1 × 2 - 1 × 2", "Gris clair", 2],
  ["99780", "Support 1 × 2 - 1 × 2 relevé", "Gris foncé", 3],
  ["3062", "Brique ronde 1 × 1", "Bleu clair transparent", 4],
  ["2921 / 28917", "Brique 1 × 1 avec poignée", "Gris clair", 2],
  ["4070 / 30069", "Brique 1 × 1 avec phare", "Gris clair", 4],
  ["30136", "Brique rondin 1 × 2", "Orange foncé", 1],
  ["3003", "Brique 2 × 2", "Noir", 2],
  ["36519 / 98100", "Cockpit du Millennium Falcon", "Gris clair", 1],
  ["3001", "Brique 2 × 4", "Blanc", 1],
  ["2570", "Arbalète", "Gris perle foncé", 1],
  ["3937", "Base de charnière 1 × 2", "Noir", 1],
  ["6134", "Haut de charnière 2 × 2", "Gris clair", 1],
  ["3024 / 6618077", "Plaque 1 × 1", "Bleu clair transparent", 2],
  ["6141 / 30057", "Plaque ronde 1 × 1", "Transparent", 2],
  ["6141 / 30057", "Plaque ronde 1 × 1", "Rouge transparent", 4],
  ["28626 / 85861", "Plaque ronde 1 × 1 à tenon ouvert", "Gris clair", 1],
  ["3023", "Plaque 1 × 2", "Beige foncé", 6],
  ["15573", "Plaque 1 × 2 à un tenon", "Rouge foncé", 1],
  ["15573", "Plaque 1 × 2 à un tenon", "Gris clair", 3],
  ["15403", "Plaque 1 × 2 avec lanceur", "Gris clair", 2],
  ["92280", "Plaque 1 × 2 avec clip", "Gris clair", 1],
  ["3710", "Plaque 1 × 4", "Gris clair", 1],
  ["2654 / 28558", "Plaque ronde 2 × 2 à fond arrondi", "Gris foncé", 4],
  ["3021", "Plaque 2 × 3", "Gris clair", 1],
  ["2639", "Plaque d'angle 4 × 4", "Gris foncé", 1],
  ["30565", "Plaque d'angle arrondie 4 × 4", "Gris foncé", 4],
  ["11213", "Plaque ronde 6 × 6 avec trou", "Gris clair", 2],
  ["4697", "Raccord en T", "Gris clair", 1],
  ["50746 / 54200", "Pente 1 × 1 à 31°", "Gris clair", 3],
  ["50746 / 54200", "Pente 1 × 1 à 31°", "Brun transparent", 1],
  ["11477", "Pente courbe 1 × 2", "Gris clair", 1],
  ["15068 / 118553", "Pente courbe 2 × 2", "Gris clair", 1],
  ["98138", "Tuile ronde 1 × 1", "Noir", 6],
  ["3070 / 113480", "Tuile 1 × 1", "Rouge foncé", 2],
  ["2412 / 30244", "Tuile grille 1 × 2", "Argenté", 4],
  ["15535", "Tuile ronde 2 × 2 avec trou", "Gris clair", 1],
  ["33909", "Tuile 2 × 2 à tenons sur le bord", "Brun rougeâtre", 1],
  ["15392", "Gâchette de lanceur", "Gris foncé", 2],
  ["6565", "Brique biseautée 3 × 2 gauche", "Gris clair", 1],
  ["6564", "Brique biseautée 3 × 2 droite", "Gris clair", 1],
  ["26601", "Plaque 2 × 2 à angle coupé", "Gris clair", 2],
  ["43722", "Plaque aile 2 × 3 droite", "Gris clair", 1],
  ["54384", "Plaque aile 3 × 6 gauche", "Gris foncé", 1],
  ["54384", "Plaque aile 3 × 6 gauche", "Gris clair", 1],
  ["54383", "Plaque aile 3 × 6 droite", "Gris foncé", 1],
];
const colors = {
  "Gris clair": "#b6bdc2", "Gris foncé": "#626b73", "Bleu clair transparent": "#8bc5df",
  "Orange foncé": "#ae5b26", "Noir": "#333333", "Blanc": "#eeeeee",
  "Gris perle foncé": "#777b80", "Transparent": "#dfeef1", "Rouge transparent": "#c83e3e",
  "Beige foncé": "#a99875", "Rouge foncé": "#842b2b", "Brun transparent": "#765c4d",
  "Argenté": "#acb4b9", "Brun rougeâtre": "#844b33", "Figurine": "#704632",
  "Brun foncé": "#57392a",
};
const pieces = Object.fromEntries(inventory.map(([reference, name, color, quantity], index) => [
  `part${index}`, { reference, name, color, quantity, image: `part${index}.${index === 20 ? "png" : "jpg"}` },
]));
Object.assign(pieces, {
  figure: { name: "Chewbacca avec bandoulière", reference: "Chewbacca", color: "Figurine", quantity: 1, image: "figure.jpg" },
  head: { name: "Tête de Chewbacca", reference: "16781", color: "Brun foncé", quantity: 1, image: "head.jpg" },
  torso: { name: "Torse avec bras et mains", reference: "73403 / 76382", color: "Brun foncé", quantity: 1, image: "torso.jpg" },
  legs: { name: "Hanches et jambes de Chewbacca", reference: "16782 / 73200", color: "Brun foncé", quantity: 1, image: "legs.jpg" },
});
const figureParts = ["head", "torso", "legs"];
const setParts = [...inventory.map((_, index) => `part${index}`), "figure"];
const groups = [...new Set(setParts.map((key) => pieces[key].color))];
const trackedTotal = setParts.reduce((total, key) => total + pieces[key].quantity, 0);
const initialState = Object.fromEntries([...setParts.filter((key) => key !== "figure"), ...figureParts].map((key) => [key, 0]));
Object.assign(initialState, { part0: 2, part16: 1, head: 1 });
const state = { ...initialState };
const initialStock = Object.fromEntries(setParts.map((key) => [key, key === "part8" ? 2 : 0]));
const stock = { ...initialStock };

function missing(key) {
  return key === "figure" ? Number(figureParts.some((part) => state[part] > 0)) : state[key];
}

function image(key) {
  return `<img class="demo-part-image" src="demo-images/${pieces[key].image}" alt="" loading="lazy" decoding="async">`;
}

function controls(key, compact = false) {
  const name = pieces[key].name;
  return `<div class="demo-piece-controls${compact ? " is-compact" : ""}">
    <span><b data-missing="${key}"></b>/${pieces[key].quantity}<small> à trouver</small></span>
    <div class="demo-control-buttons">
      <button type="button" class="demo-check" data-key="${key}" data-complete-part aria-label="Tout trouver : ${name}" title="Tout trouvé">✓</button>
      <button type="button" data-key="${key}" data-change="-1" aria-label="Marquer une pièce ${name} comme trouvée">−</button>
      <button type="button" data-key="${key}" data-change="1" aria-label="Marquer une pièce ${name} comme manquante">+</button>
    </div>
  </div>`;
}

function partCard(key) {
  const part = pieces[key];
  return `<article class="demo-part-card">
    <div class="demo-image-box">${image(key)}<span class="demo-part-color">${part.color}</span><strong title="${part.name} · Réf. ${part.reference}">${part.name}</strong></div>
    ${controls(key)}
  </article>`;
}

function figureCard() {
  return `${partCard("figure")}<details class="demo-figure-parts"><summary>Pièces de cette figurine · 3 pièces</summary><small>La figurine est trouvée lorsque toutes ses pièces le sont.</small><div class="demo-figure-grid">${figureParts.map(partCard).join("")}</div></details>`;
}

function collectionCard(key) {
  const part = pieces[key];
  return `<article class="demo-collection-part">
    <div class="demo-collection-image">${image(key)}</div>
    <div class="demo-collection-copy"><strong title="${part.name}">${part.name}</strong><span>Réf. ${part.reference} · ${part.color}</span></div>
    ${controls(key, true)}
  </article>`;
}

function collectionGroup(color, inventoryView = false) {
  const keys = setParts.filter((key) => pieces[key].color === color);
  return `<details class="demo-collection-color" data-collection-group style="--group-color:${colors[color]}" open>
    <summary><span class="demo-swatch" style="background:${colors[color]}"></span><strong>${color}</strong><small>${keys.length} référence(s)</small><span aria-hidden="true">⌄</span></summary>
    <div class="demo-collection-grid">${keys.map(inventoryView ? inventoryCard : collectionCard).join("")}</div>
  </details>`;
}

function listRow(key, showControls) {
  const part = pieces[key];
  return `<article class="demo-list-row" data-row="${key}">
    ${image(key)}<div><strong>${part.name}</strong><small>${part.color} · ${part.quantity} dans le set</small></div>
    ${showControls ? controls(key) : `<span class="demo-list-quantity"><b data-found="${key}"></b> trouvé(s)</span>`}
  </article>`;
}

function inventoryCard(key) {
  const part = pieces[key];
  return `<article class="demo-collection-part" data-inventory-key="${key}">
      <div class="demo-collection-image">${image(key)}</div>
      <div class="demo-collection-copy"><strong title="${part.name}">${part.name}</strong><span>Réf. ${part.reference}</span></div>
      <div class="demo-inventory-detail">sets · <b data-found="${key}"></b> pièce(s)</div>
      <div class="demo-stock-row"><span>vrac</span><b data-stock="${key}"></b><div class="demo-control-buttons">
        <button type="button" data-stock-key="${key}" data-stock-change="-1" aria-label="Retirer une pièce ${part.name} du vrac">−</button>
        <button type="button" data-stock-key="${key}" data-stock-change="1" aria-label="Ajouter une pièce ${part.name} au vrac">+</button>
      </div></div>
    </article>`;
}

app.querySelector("#demo-color").insertAdjacentHTML("beforeend", groups.map((color) => `<option>${color}</option>`).join(""));
app.querySelector(".demo-groups").innerHTML = groups.map((color) => {
  const keys = setParts.filter((key) => pieces[key].color === color);
  const quantity = keys.reduce((total, key) => total + pieces[key].quantity, 0);
  return `<details class="demo-color-group" data-group="${color}" style="--group-color:${colors[color]}" open>
    <summary><span class="demo-swatch" style="background:${colors[color]}"></span><strong>${color}</strong><small>${keys.length} référence(s)</small><span><b data-group-missing="${color}"></b> / ${quantity} à trouver</span></summary>
    <div class="demo-parts-grid">${keys.map((key) => `<div data-card="${key}">${key === "figure" ? figureCard() : partCard(key)}</div>`).join("")}</div>
  </details>`;
}).join("");
app.querySelector("#demo-collection-parts").innerHTML = groups.map((color) => collectionGroup(color)).join("");
app.querySelector("#demo-inventory-list").innerHTML = groups.map((color) => collectionGroup(color, true)).join("");
app.querySelector("#demo-missing-list").innerHTML = setParts.map((key) => listRow(key, true)).join("");

function update(announce = false) {
  const totalMissing = setParts.reduce((total, key) => total + missing(key), 0);
  app.querySelectorAll("[data-missing]").forEach((element) => {
    element.textContent = missing(element.dataset.missing);
  });
  app.querySelectorAll("[data-found]").forEach((element) => {
    const key = element.dataset.found;
    element.textContent = pieces[key].quantity - missing(key);
  });
  app.querySelectorAll("[data-total-missing]").forEach((element) => { element.textContent = totalMissing; });
  app.querySelectorAll("[data-total-found]").forEach((element) => { element.textContent = trackedTotal - totalMissing; });
  app.querySelectorAll("[data-group-missing]").forEach((element) => {
    element.textContent = setParts.filter((key) => pieces[key].color === element.dataset.groupMissing)
      .reduce((total, key) => total + missing(key), 0);
  });
  const stockTotal = setParts.reduce((total, key) => total + stock[key], 0);
  app.querySelectorAll("[data-stock]").forEach((element) => { element.textContent = stock[element.dataset.stock]; });
  app.querySelector("[data-stock-total]").textContent = stockTotal;
  app.querySelector("[data-inventory-total]").textContent = trackedTotal - totalMissing + stockTotal;
  app.querySelectorAll("[data-inventory-key]").forEach((group) => {
    const key = group.dataset.inventoryKey;
    group.hidden = pieces[key].quantity - missing(key) + stock[key] === 0;
  });
  app.querySelectorAll("#demo-inventory-list [data-collection-group]").forEach((group) => {
    group.hidden = !group.querySelector("[data-inventory-key]:not([hidden])");
  });
  app.querySelectorAll("[data-stock-change]").forEach((button) => {
    button.disabled = Number(button.dataset.stockChange) < 0 && stock[button.dataset.stockKey] === 0;
  });
  app.querySelectorAll("[data-change]").forEach((button) => {
    const count = missing(button.dataset.key);
    button.disabled = Number(button.dataset.change) < 0 ? count === 0 : count === pieces[button.dataset.key].quantity;
  });
  app.querySelectorAll("[data-complete-part]").forEach((button) => {
    button.disabled = missing(button.dataset.key) === 0;
  });
  app.querySelectorAll(".demo-collection-part").forEach((card) => {
    const key = card.querySelector("[data-complete-part]")?.dataset.key;
    card.classList.toggle("is-found", Boolean(key) && missing(key) === 0);
  });
  const completeSet = app.querySelector("[data-complete-set]");
  completeSet.textContent = totalMissing ? "✓ Tout trouvé" : "↻ Tout chercher";
  app.querySelectorAll("#demo-missing-list [data-row]").forEach((row) => {
    row.hidden = missing(row.dataset.row) === 0;
  });
  app.querySelector("#demo-all-found").hidden = totalMissing !== 0;
  if (announce) {
    app.querySelector("#demo-announcement").textContent = `${totalMissing} pièce${totalMissing === 1 ? "" : "s"} à réunir.`;
  }
}

function filterPieces() {
  const query = app.querySelector("#demo-search").value.trim().toLocaleLowerCase("fr");
  const color = app.querySelector("#demo-color").value.toLocaleLowerCase("fr");
  let visible = 0;
  app.querySelectorAll("[data-group]").forEach((group) => {
    let groupVisible = 0;
    group.querySelectorAll("[data-card]").forEach((card) => {
      const part = pieces[card.dataset.card];
      const matches = `${part.name} ${part.reference} ${part.color}`.toLocaleLowerCase("fr").includes(query)
        && (!color || group.dataset.group.toLocaleLowerCase("fr") === color);
      card.hidden = !matches;
      if (matches) groupVisible += 1;
    });
    group.hidden = groupVisible === 0;
    visible += groupVisible;
  });
  app.querySelector("#demo-no-results").hidden = visible > 0;
}

app.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.view) {
    app.querySelectorAll("[data-view]").forEach((item) => item.removeAttribute("aria-current"));
    button.setAttribute("aria-current", "page");
    app.querySelectorAll("[data-screen]").forEach((screen) => { screen.hidden = screen.dataset.screen !== button.dataset.view; });
    app.querySelector("#demo-breadcrumb").textContent = button.textContent.trim().replace(/\s+\d+$/, "").toLocaleUpperCase("fr");
  } else if (button.dataset.stockChange) {
    const key = button.dataset.stockKey;
    stock[key] = Math.max(0, stock[key] + Number(button.dataset.stockChange));
    update(true);
  } else if (button.hasAttribute("data-complete-part")) {
    const key = button.dataset.key;
    if (key === "figure") figureParts.forEach((part) => { state[part] = 0; });
    else state[key] = 0;
    update(true);
  } else if (button.dataset.change) {
    const key = button.dataset.key;
    if (key === "figure") {
      const value = Number(button.dataset.change) < 0 ? 0 : 1;
      figureParts.forEach((part) => { state[part] = value; });
    } else {
      state[key] = Math.max(0, Math.min(pieces[key].quantity, state[key] + Number(button.dataset.change)));
    }
    update(true);
  } else if (button.hasAttribute("data-complete-set")) {
    const complete = setParts.some((key) => missing(key) > 0);
    Object.keys(state).forEach((key) => { state[key] = complete ? 0 : pieces[key].quantity; });
    update(true);
  } else if (button.id === "demo-reset") {
    Object.assign(state, initialState);
    Object.assign(stock, initialStock);
    app.querySelector("#demo-search").value = "";
    app.querySelector("#demo-color").value = "";
    filterPieces();
    update(true);
  }
});

app.querySelector("#demo-search").addEventListener("input", filterPieces);
app.querySelector("#demo-color").addEventListener("change", filterPieces);
update();
