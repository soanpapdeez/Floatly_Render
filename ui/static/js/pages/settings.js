// Settings: canvas colour, motion status, policy panel switch.
import { setCanvas, applyOwner } from "../shell.js";
import { $, $$, reducedMotion, store, ownerInitials, toast } from "../util.js";

const sync = () => $$(".swatch[data-canvas]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.canvas === (document.documentElement.dataset.canvas || "plum"))));
$$(".swatch[data-canvas]").forEach((b) => b.addEventListener("click", () => { setCanvas(b.dataset.canvas); sync(); }));
document.addEventListener("float:canvas", sync);
sync();
$("#motion").textContent = reducedMotion() ? "reduced (system)" : "on";
document.addEventListener("float:view", (e) => $$("[data-panel]").forEach((p) => (p.hidden = p.dataset.panel !== e.detail.view)));

// Account: display name kept in this browser (no login in this demo)
const nameInput = $("#acct-name");
nameInput.value = store.get("owner", "") || "";
const preview = () => { $("#acct-avatar").textContent = ownerInitials(nameInput.value.trim() || window.FLOAT_BOOT.owner); };
nameInput.addEventListener("input", preview);
preview();
$("#acct-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = nameInput.value.trim();
  store.set("owner", v || null);
  applyOwner();
  toast(v ? `Saved. Welcome back, ${v}.` : "Name cleared.", "ok");
});
$("#acct-reset").addEventListener("click", () => { nameInput.value = ""; store.set("owner", null); applyOwner(); preview(); toast("Back to the default name.", "info"); });
if (location.hash === "#account") nameInput.focus();
