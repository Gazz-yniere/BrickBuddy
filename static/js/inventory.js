/* Pièces : compteurs de sets, figurines, vrac et totaux de l'inventaire. */

function updateStockHint(card) {
  const hint = card?.querySelector(".stock-hint");
  if (!hint) {
    return;
  }
  const missing = [...card.querySelectorAll(".set-status-form .set-missing-count")].reduce(
    (total, count) => total + Number(count.textContent),
    0,
  );
  const stock = Number(hint.dataset.stock) || 0;
  hint.hidden = missing === 0;
  hint.classList.toggle("stock-enough", stock >= missing);
  hint.classList.toggle("stock-partial", stock < missing);
  hint.querySelector("[data-stock-status]").textContent =
    `Vrac : ${stock} ${stock >= missing ? "· suffisant" : `· insuffisant (${missing} requis)`}`;
}

function updateMinifigComponent(form, missing) {
  const component = form.closest(".minifig-part");
  const quantity = Number(form.dataset.quantity);
  const isComplete = missing === 0;
  form.querySelector(".set-missing-count").textContent = missing;
  form.classList.toggle("is-complete", isComplete);
  component.classList.toggle("is-found", isComplete);
  const total = component.querySelector(".minifig-part-missing-total strong");
  total.textContent = missing;
  total.classList.toggle("accent-found", isComplete);
  total.classList.toggle("accent-missing", !isComplete);
  form.querySelector('button[name="change"][value="-1"]').disabled = isComplete;
  form.querySelector('button[name="change"][value="1"]').disabled = missing >= quantity;
  form.querySelector(".set-complete-part").disabled = isComplete;
}

function updateColorGroup(group) {
  if (!(group instanceof HTMLDetailsElement)) {
    return;
  }
  if (!group.querySelector(".piece-card")) {
    group.remove();
    return;
  }
  if (group.hasAttribute("data-group-key")) {
    const grid = group.querySelector(".parts-grid");
    const cards = [...grid.children];
    cards.sort((first, second) =>
      Number(first.classList.contains("is-found")) - Number(second.classList.contains("is-found")) ||
      Number(first.dataset.gatheringOrder) - Number(second.dataset.gatheringOrder),
    );
    cards.forEach((card, index) => {
      if (grid.children[index] !== card) {
        grid.insertBefore(card, grid.children[index]);
      }
    });
  }
  const referenceCount = group.querySelectorAll(".piece-card").length;
  group.querySelector(".color-heading span").textContent =
    `${referenceCount} référence${referenceCount === 1 ? "" : "s"}`;
  const missing = [...group.querySelectorAll(".part-missing-total strong")].reduce(
    (total, count) => total + Number(count.textContent),
    0,
  );
  group.dataset.missing = String(missing);
  const total = group.querySelector("[data-color-missing]");
  total.textContent = String(missing);
  total.classList.toggle("accent-found", missing === 0);
  total.classList.toggle("accent-missing", missing > 0);
  const quantityTotal = [...group.querySelectorAll(".part-missing-total")].reduce(
    (sum, element) => sum + (Number(element.dataset.quantity) || 0),
    0,
  );
  const colorTotal = group.querySelector("[data-color-total]");
  if (colorTotal) {
    colorTotal.textContent = `/${quantityTotal}`;
  }
  group.open = missing > 0;
}

function refreshPieceCard(card) {
  if (!card) {
    return;
  }
  const missing = [...card.querySelectorAll(".set-status-form .set-missing-count")].reduce(
    (total, count) => total + Number(count.textContent),
    0,
  );
  const total = card.querySelector(".part-missing-total strong");
  if (total) {
    total.textContent = String(missing);
    total.classList.toggle("accent-found", missing === 0);
    total.classList.toggle("accent-missing", missing > 0);
  }
  card.classList.toggle("is-found", missing === 0);
  updateStockHint(card);
  updateColorGroup(card.closest("[data-color-group]"));
}

function removeCompletedGatheringSet(setId) {
  document.querySelectorAll(`.set-status-form[data-set-id="${setId}"]`).forEach((setForm) => {
    const card = setForm.closest(".piece-card");
    const colorGroup = card?.closest("[data-color-group]");
    const setQuantity = Number(setForm.dataset.quantity) || 0;
    setForm.remove();
    if (!card) {
      return;
    }
    card.querySelectorAll(`.minifig-parts[data-minifig-set="${setId}"]`).forEach((details) => details.remove());
    const partMissingTotal = card.querySelector(".part-missing-total");
    if (partMissingTotal) {
      const remaining = Math.max(0, Number(partMissingTotal.dataset.quantity || 0) - setQuantity);
      partMissingTotal.dataset.quantity = String(remaining);
      partMissingTotal.querySelector(".part-total").textContent = `/${remaining}`;
    }
    if (!card.querySelector(".set-status-form")) {
      card.remove();
      updateColorGroup(colorGroup);
    } else {
      refreshPieceCard(card);
    }
  });
  document.querySelector(`.candidate-grid .set-card[data-set-id="${setId}"]`)?.remove();
  const setCount = document.querySelector("[data-gathering-set-count]");
  if (setCount) {
    setCount.textContent = document.querySelectorAll(".candidate-grid .set-card").length;
  }
  const summary = document.querySelector("[data-gathering-part-summary]");
  if (summary) {
    const partCount = document.querySelectorAll(".color-groups .piece-card").length;
    const colorCount = document.querySelectorAll(".color-groups [data-color-group]").length;
    summary.textContent = `${partCount} référence${partCount === 1 ? "" : "s"} · ${colorCount} couleur${colorCount === 1 ? "" : "s"}`;
  }
}

function refreshInventoryTotals(group) {
  if (group instanceof HTMLElement) {
    const cards = [...group.querySelectorAll(".inventory-part-card")];
    if (cards.length === 0) {
      group.remove();
    } else {
      const quantity = cards.reduce(
        (sum, card) => sum + (Number(card.dataset.total) || 0),
        0,
      );
      const colorTotal = group.querySelector(".color-totals strong");
      if (colorTotal) {
        colorTotal.textContent = String(quantity);
      }
      const referenceLabel = group.querySelector(".color-heading span");
      if (referenceLabel) {
        referenceLabel.textContent = `${cards.length} référence${cards.length === 1 ? "" : "s"}`;
      }
    }
  }

  const groups = [...document.querySelectorAll(".inventory-color")];
  const partCount = groups.reduce(
    (sum, item) => sum + item.querySelectorAll(".inventory-part-card").length,
    0,
  );
  const totalQuantity = groups.reduce(
    (sum, item) =>
      sum +
      [...item.querySelectorAll(".inventory-part-card")].reduce(
        (groupSum, card) => groupSum + (Number(card.dataset.total) || 0),
        0,
      ),
    0,
  );

  const heading = document.querySelector(".results-heading");
  if (heading) {
    heading.dataset.partCount = String(partCount);
    heading.dataset.colorCount = String(groups.length);
    heading.dataset.totalQuantity = String(totalQuantity);
    const partLabel = heading.querySelector("[data-part-count-label]");
    if (partLabel) {
      partLabel.textContent = `${partCount} référence${partCount === 1 ? "" : "s"}`;
    }
    const summary = heading.querySelector("[data-color-summary]");
    if (summary) {
      summary.replaceChildren(
        document.createTextNode(
          `${groups.length} couleur${groups.length === 1 ? "" : "s"} · `,
        ),
      );
      const quantity = document.createElement("span");
      quantity.dataset.totalQuantityLabel = "";
      quantity.textContent = String(totalQuantity);
      summary.append(quantity, document.createTextNode(" pièces"));
    }
    if (groups.length === 0) {
      heading.remove();
      document.querySelector(".origin-legend")?.remove();
    }
  }
}

// Nom de couleur repris du menu déroulant : le champ caché part avec le formulaire.
function syncStockColorName(select) {
  const field = document.getElementById("stock-color-name");
  if (field) {
    field.value = select.options[select.selectedIndex]?.dataset.name ?? "";
  }
}

document.querySelectorAll("#stock-color").forEach(syncStockColorName);

// Après une mise à jour sans rechargement, le menu déroulant est nouveau :
// le champ caché reprend la couleur affichée.
document.addEventListener("page-updated", () => {
  document.querySelectorAll("#stock-color").forEach(syncStockColorName);
});

document.addEventListener("change", (event) => {
  const select = event.target;
  if (select instanceof HTMLSelectElement && select.id === "stock-color") {
    syncStockColorName(select);
  }
});

document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !form.matches(".set-status-form")) {
    return;
  }

  event.preventDefault();
  const button = event.submitter;
  if (!(button instanceof HTMLButtonElement) || !button.name || form.dataset.pending) {
    return;
  }

  form.dataset.pending = "true";
  form.querySelectorAll("button").forEach((control) => {
    control.disabled = true;
  });

  const body = new FormData(form);
  body.set(button.name, button.value);

  try {
    const response = await fetch(form.action, {
      method: "POST",
      body,
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "La quantité n'a pas pu être mise à jour.");
    }
    if (result.components) {
      for (const component of result.components) {
        const componentForm = document.querySelector(
          `.minifig-part-status-form[action$="/minifig-parts/${component.id}/status"]`,
        );
        if (componentForm) {
          updateMinifigComponent(componentForm, component.missing_quantity);
        }
      }
    }

    const isComplete = result.missing === 0;
    const missingCount = form.querySelector(".set-missing-count");
    missingCount.textContent = result.missing;
    const missingLabel = `${result.missing} pièce${result.missing === 1 ? "" : "s"} manquante${result.missing === 1 ? "" : "s"}`;
    form.setAttribute("aria-label", missingLabel);
    if (missingCount.hasAttribute("aria-label")) {
      missingCount.setAttribute("aria-label", missingLabel);
    }
    const collectionCount = form.querySelector(".collection-part-count");
    if (collectionCount) {
      collectionCount.setAttribute("aria-label", `${missingLabel} sur ${result.quantity}`);
    }
    form.classList.toggle("is-complete", isComplete);
    form.closest(".collection-part-card")?.classList.toggle("part-done", isComplete);
    form.querySelector('button[name="change"][value="-1"]').disabled = isComplete;
    form.querySelector('button[name="change"][value="1"]').disabled =
      result.missing === result.quantity;
    const completeButton = form.querySelector(".set-complete-part");
    if (completeButton) {
      completeButton.disabled = isComplete;
    }

    const pieceCard = form.closest(".piece-card");
    if (result.gathering_complete && pieceCard) {
      removeCompletedGatheringSet(result.set_id);
    } else if (pieceCard) {
      const partTotal = pieceCard.querySelector(".part-missing-total strong");
      partTotal.textContent = result.part_missing;
      partTotal.classList.toggle("accent-found", result.part_missing === 0);
      partTotal.classList.toggle("accent-missing", result.part_missing > 0);
      pieceCard.classList.toggle("is-found", result.part_missing === 0);
      if (form.querySelector('input[name="return_to"]')?.value === "missing") {
        const total = document.querySelector("#missing-parts-total");
        if (total) {
          total.textContent = result.total_missing;
        }
        if (result.part_missing === 0) {
          pieceCard.remove();
        }
      }
      updateColorGroup(pieceCard.closest("[data-color-group]"));
    }

    const setCard = document.querySelector(`.set-card[data-set-id="${result.set_id}"]`);
    if (setCard) {
      setCard.querySelector(".set-progress strong").textContent = result.set_missing;
      const completeButton = setCard.querySelector(
        ".candidate-actions button[type='submit']",
      );
      if (completeButton) {
        completeButton.disabled = result.set_missing === 0;
      }
    }
    await refreshCurrentPage();
  } catch (error) {
    showInteractionError(
      error instanceof Error ? error.message : "La quantité n'a pas pu être mise à jour.",
    );
  } finally {
    delete form.dataset.pending;
    const missing = Number(form.querySelector(".set-missing-count").textContent);
    const quantity = Number(form.dataset.quantity);
    form.querySelector('button[name="change"][value="-1"]').disabled = missing === 0;
    form.querySelector('button[name="change"][value="1"]').disabled =
      Number.isFinite(quantity) && missing >= quantity;
    const completeButton = form.querySelector(".set-complete-part");
    if (completeButton) {
      completeButton.disabled = missing === 0;
    }
    updateStockHint(form.closest(".piece-card"));
  }
});

document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (
    !(form instanceof HTMLFormElement) ||
    !form.matches(".minifig-part-status-form") ||
    form.dataset.pending
  ) {
    return;
  }

  event.preventDefault();
  const button = event.submitter;
  if (!(button instanceof HTMLButtonElement) || !button.name) {
    return;
  }

  form.dataset.pending = "true";
  const controls = [...form.querySelectorAll("button")];
  const disabledStates = controls.map((control) => control.disabled);
  controls.forEach((control) => { control.disabled = true; });
  const body = new FormData(form);
  body.set(button.name, button.value);
  let responseSucceeded = false;

  try {
    const response = await fetch(form.action, {
      method: "POST",
      body,
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Le statut de cette pièce n'a pas pu être mis à jour.");
    }

    updateMinifigComponent(form, result.missing_quantity);
    const card = form.closest(".piece-card");
    const parentForm = card.querySelector(
      `.set-status-form[action$="/parts/${result.parent_id}/missing"]`,
    );
    if (result.gathering_complete) {
      removeCompletedGatheringSet(result.set_id);
    } else if (parentForm) {
      const isComplete = result.missing === 0;
      const count = parentForm.querySelector(".set-missing-count");
      count.textContent = result.missing;
      count.setAttribute("aria-label", `${result.missing} pièce${result.missing === 1 ? "" : "s"} manquante${result.missing === 1 ? "" : "s"}`);
      parentForm.classList.toggle("is-complete", isComplete);
      parentForm.querySelector('button[name="change"][value="-1"]').disabled = isComplete;
      parentForm.querySelector('button[name="change"][value="1"]').disabled =
        result.missing >= result.parent_quantity;
      parentForm.querySelector(".set-complete-part").disabled = isComplete;
      refreshPieceCard(card);
      const setCard = document.querySelector(`.candidate-grid .set-card[data-set-id="${result.set_id}"]`);
      if (setCard) {
        setCard.querySelector(".set-progress strong").textContent = result.set_missing;
      }
    }
    responseSucceeded = true;
    await refreshCurrentPage();
  } catch (error) {
    showInteractionError(
      error instanceof Error
        ? error.message
        : "Le statut de cette pièce n'a pas pu être mis à jour.",
    );
  } finally {
    delete form.dataset.pending;
    if (form.isConnected && !responseSucceeded) {
      controls.forEach((control, index) => { control.disabled = disabledStates[index]; });
    }
  }
});

document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !form.matches(".stock-take-form") || form.dataset.pending) {
    return;
  }
  event.preventDefault();
  form.dataset.pending = "true";
  const button = form.querySelector("button");
  startLoading(button);
  button.disabled = true;
  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Impossible de prendre dans le vrac.");
    }
    // Une figurine prise dans le vrac change les composants affichés : la page
    // est redemandée et remplacée, jamais rechargée, et le vrac n'est pas compté deux fois.
    if (result.updates.some((update) => update.item_type === "minifig")) {
      await refreshCurrentPage();
      return;
    }
    const card = form.closest(".piece-card");
    for (const update of result.updates) {
      const setForm = card.querySelector(`.set-status-form[action$="/parts/${update.part_id}/missing"]`);
      if (!setForm) {
        continue;
      }
      setForm.querySelector(".set-missing-count").textContent = update.missing;
      setForm.classList.toggle("is-complete", update.missing === 0);
      setForm.querySelector('button[name="change"][value="-1"]').disabled = update.missing === 0;
      setForm.querySelector('button[name="change"][value="1"]').disabled =
        update.missing >= Number(setForm.dataset.quantity);
      const completeButton = setForm.querySelector(".set-complete-part");
      if (completeButton) {
        completeButton.disabled = update.missing === 0;
      }
    }
    const hint = form.closest(".stock-hint");
    hint.dataset.stock = String(result.stock_qty);
    if (result.stock_qty === 0) {
      hint.remove();
    }
    refreshPieceCard(card);
    await refreshCurrentPage();
  } catch (error) {
    showInteractionError(error instanceof Error ? error.message : "Impossible de prendre dans le vrac.");
  } finally {
    delete form.dataset.pending;
    stopLoading(button);
    button.disabled = false;
  }
});

document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (
    !(form instanceof HTMLFormElement) ||
    !form.matches(".stock-step-form, .stock-add-form, .add-stock-form") ||
    form.dataset.pending
  ) {
    return;
  }

  event.preventDefault();
  form.dataset.pending = "true";
  const controls = [...form.querySelectorAll("button")];
  const previousStates = controls.map((control) => control.disabled);
  controls.forEach((control) => {
    control.disabled = true;
  });

  const button = event.submitter;
  const body = new FormData(form);
  if (button instanceof HTMLButtonElement && button.name) {
    body.set(button.name, button.value);
  }

  try {
    const response = await fetch(form.action, {
      method: "POST",
      body,
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Le vrac n'a pas pu être mis à jour.");
    }

    // Le panneau d'ajout n'a pas de carte à re-render : la page redemandée
    // affiche la nouvelle entrée, le message du serveur et les compteurs.
    const card = form.closest(".inventory-part-card");
    const group = card?.closest(".inventory-color") || null;
    if (result.removed) {
      card?.remove();
    } else if (card && result.html) {
      const template = document.createElement("template");
      template.innerHTML = result.html.trim();
      const replacement = template.content.firstElementChild;
      if (replacement) {
        card.replaceWith(replacement);
      }
    }
    refreshInventoryTotals(group);
    await refreshCurrentPage();
  } catch (error) {
    previousStates.forEach((disabled, index) => {
      controls[index].disabled = disabled;
    });
    showInteractionError(
      error instanceof Error ? error.message : "Le vrac n'a pas pu être mis à jour.",
    );
  } finally {
    delete form.dataset.pending;
  }
});
