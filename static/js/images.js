/* Visuels : couverture LEGO indisponible, remplacée par le visuel vide. */

document.addEventListener("error", (event) => {
  const image = event.target;
  if (!(image instanceof HTMLImageElement)) {
    return;
  }
  const thumb = image.closest(".instruction-card-thumb");
  if (!(thumb instanceof HTMLElement)) {
    return;
  }
  image.remove();
  if (thumb.querySelector(".instruction-cover-empty")) {
    return;
  }
  const placeholder = document.createElement("span");
  placeholder.className = "instruction-cover-empty";
  placeholder.setAttribute("aria-hidden", "true");
  placeholder.textContent = "▤";
  thumb.prepend(placeholder);
}, true);
