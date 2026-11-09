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
  dialog.querySelector("[data-confirm-message]").textContent =
    form.dataset.confirmMessage || "Confirmer cette action ?";
  dialog.addEventListener(
    "close",
    () => {
      if (dialog.returnValue === "confirm") {
        form.dataset.confirmed = "true";
        form.requestSubmit();
      }
    },
    { once: true },
  );
  dialog.showModal();
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

    const isComplete = result.missing === 0;
    form.querySelector(".set-missing-count").textContent = result.missing;
    form.setAttribute(
      "aria-label",
      `${result.missing} pièce${result.missing === 1 ? "" : "s"} manquante${result.missing === 1 ? "" : "s"}`,
    );
    form.classList.toggle("is-complete", isComplete);
    form.querySelector('button[name="change"][value="-1"]').disabled = isComplete;
    form.querySelector('button[name="change"][value="1"]').disabled =
      result.missing === result.quantity;
    const completeButton = form.querySelector(".set-complete-part");
    if (completeButton) {
      completeButton.disabled = isComplete;
    }

    const pieceCard = form.closest(".piece-card");
    if (result.gathering_complete) {
      document
        .querySelectorAll(`.set-status-form[data-set-id="${result.set_id}"]`)
        .forEach((setForm) => {
          const card = setForm.closest(".piece-card");
          const colorGroup = card?.closest("[data-color-group]");
          setForm.remove();
          if (!card) {
            return;
          }
          const missing = [...card.querySelectorAll(".set-status-form .set-missing-count")]
            .reduce((total, count) => total + Number(count.textContent), 0);
          const total = card.querySelector(".part-missing-total strong");
          total.textContent = String(missing);
          total.classList.toggle("accent-found", missing === 0);
          total.classList.toggle("accent-missing", missing > 0);
          if (!card.querySelector(".set-status-form")) {
            card.remove();
          }
          updateColorGroup(colorGroup);
        });
      document
        .querySelector(`.candidate-grid .set-card[data-set-id="${result.set_id}"]`)
        ?.remove();
    } else if (pieceCard) {
      const partTotal = pieceCard.querySelector(".part-missing-total strong");
      partTotal.textContent = result.part_missing;
      partTotal.classList.toggle("accent-found", result.part_missing === 0);
      partTotal.classList.toggle("accent-missing", result.part_missing > 0);
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
  } catch (error) {
    const messages = document.querySelector("#interaction-messages");
    messages.replaceChildren();
    const message = document.createElement("div");
    message.className = "flash error";
    message.textContent =
      error instanceof Error ? error.message : "La quantité n'a pas pu être mise à jour.";
    messages.append(message);
    messages.hidden = false;
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
  }
});

function updateColorGroup(group) {
  if (!(group instanceof HTMLDetailsElement)) {
    return;
  }
  if (!group.querySelector(".piece-card")) {
    group.remove();
    return;
  }
  const missing = [...group.querySelectorAll(".part-missing-total strong")].reduce(
    (total, count) => total + Number(count.textContent),
    0,
  );
  group.dataset.missing = String(missing);
  const total = group.querySelector("[data-color-missing]");
  total.textContent = String(missing);
  total.classList.toggle("accent-found", missing === 0);
  total.classList.toggle("accent-missing", missing > 0);
  group.open = missing > 0;
}
