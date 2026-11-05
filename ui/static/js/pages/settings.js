// Settings: canvas colour, motion status, policy panel switch.
import { setCanvas } from "../shell.js";
import { $, $$, reducedMotion } from "../util.js";

const sync = () => $$(".swatch[data-canvas]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.canvas === (document.documentElement.dataset.canvas || "plum"))));
$$(".swatch[data-canvas]").forEach((b) => b.addEventListener("click", () => { setCanvas(b.dataset.canvas); sync(); }));
document.addEventListener("float:canvas", sync);
sync();
$("#motion").textContent = reducedMotion() ? "reduced (system)" : "on";
document.addEventListener("float:view", (e) => $$("[data-panel]").forEach((p) => (p.hidden = p.dataset.panel !== e.detail.view)));
