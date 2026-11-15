const app = document.querySelector("#demo-app");
const initialState = { brick: 2, plate: 1, head: 1, torso: 0, legs: 0 };
const state = { ...initialState };
const pieces = {
  brick: { name: "Brique 2 × 4", color: "Orange", quantity: 3, image: "brick" },
  plate: { name: "Plaque 1 × 2", color: "Bleu", quantity: 3, image: "plate" },
  figure: { name: "Ouvrier de l'atelier", color: "Figurine", quantity: 1, image: "figure" },
  head: { name: "Tête", color: "Jaune", quantity: 1, image: "head" },
  torso: { name: "Torse", color: "Orange", quantity: 1, image: "torso" },
  legs: { name: "Jambes", color: "Bleu", quantity: 1, image: "legs" },
};
const figureParts = ["head", "torso", "legs"];
const setParts = ["brick", "plate", "figure"];

function missing(key) {
  return key === "figure" ? Number(figureParts.some((part) => state[part] > 0)) : state[key];
}

function image(key) {
  return `<svg class="demo-part-image" aria-hidden="true"><use href="demo-pieces.svg#${pieces[key].image}"></use></svg>`;
}

function controls(key) {
  const name = pieces[key].name;
  return `<div class="demo-piece-controls">
    <button type="button" data-key="${key}" data-change="-1" aria-label="Marquer une pièce ${name} comme trouvée">−</button>
    <span><b data-missing="${key}"></b> / ${pieces[key].quantity}<small> à trouver</small></span>
    <button type="button" data-key="${key}" data-change="1" aria-label="Marquer une pièce ${name} comme manquante">+</button>
  </div>`;
}

function partCard(key) {
  const part = pieces[key];
  return `<article class="demo-part-card">
    <div class="demo-image-box">${image(key)}<span class="demo-part-color">${part.color}</span><strong title="${part.name}">${part.name}</strong></div>
    ${controls(key)}
  </article>`;
}

function figureCard() {
  return `${partCard("figure")}<div class="demo-figure-parts"><strong>Pièces de la figurine</strong><small>La figurine est trouvée lorsque toutes ses pièces le sont.</small><div class="demo-figure-grid">${figureParts.map(partCard).join("")}</div></div>`;
}

function listRow(key, showControls) {
  const part = pieces[key];
  return `<article class="demo-list-row" data-row="${key}">
    ${image(key)}<div><strong>${part.name}</strong><small>${part.color} · ${part.quantity} dans le set</small></div>
    ${showControls ? controls(key) : `<span class="demo-list-quantity"><b data-found="${key}"></b> trouvé(s)</span>`}
  </article>`;
}

for (const key of setParts) {
  app.querySelector(`[data-card="${key}"]`).innerHTML = key === "figure" ? figureCard() : partCard(key);
}
app.querySelector("#demo-collection-parts").innerHTML = setParts.map((key) => listRow(key, true)).join("");
app.querySelector("#demo-inventory-list").innerHTML = setParts.map((key) => listRow(key, false)).join("");
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
  app.querySelectorAll("[data-total-found]").forEach((element) => { element.textContent = 7 - totalMissing; });
  app.querySelectorAll("[data-change]").forEach((button) => {
    const count = missing(button.dataset.key);
    button.disabled = Number(button.dataset.change) < 0 ? count === 0 : count === pieces[button.dataset.key].quantity;
  });
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
    const key = group.querySelector("[data-card]").dataset.card;
    const part = pieces[key];
    const matches = `${part.name} ${part.color}`.toLocaleLowerCase("fr").includes(query)
      && (!color || group.dataset.group === color);
    group.hidden = !matches;
    if (matches) visible += 1;
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
    Object.keys(state).forEach((key) => { state[key] = 0; });
    update(true);
  } else if (button.id === "demo-reset") {
    Object.assign(state, initialState);
    app.querySelector("#demo-search").value = "";
    app.querySelector("#demo-color").value = "";
    filterPieces();
    update(true);
  }
});

app.querySelector("#demo-search").addEventListener("input", filterPieces);
app.querySelector("#demo-color").addEventListener("change", filterPieces);
update();
