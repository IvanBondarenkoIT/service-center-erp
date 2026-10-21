function fillMachineFromSuggest(id, serial, model) {
  const serialInput = document.getElementById("new_machine_serial");
  const modelInput = document.getElementById("new_machine_model");
  if (serialInput && serial) serialInput.value = serial;
  if (modelInput) modelInput.value = model || "";
}

function fillClientFromSuggest(id, phone, name) {
  const phoneInput = document.getElementById("new_client_phone");
  const nameInput = document.getElementById("new_client_name");
  if (phoneInput && phone) phoneInput.value = phone;
  if (nameInput && name) nameInput.value = name;
}

function applyErpModel(erpId, name) {
  const modelInput = document.getElementById("new_machine_model");
  const erpInput = document.getElementById("erp_goods_id");
  if (modelInput) modelInput.value = name;
  if (erpInput) erpInput.value = erpId;
  const box = document.getElementById("erp-model-suggest");
  if (box) box.replaceChildren();
}

function applyErpPart(pick) {
  const card = pick.closest("[data-line-card]");
  if (!card) return;
  const desc = card.querySelector('input[name="description"]');
  const code = card.querySelector('input[name="part_code"]');
  if (desc) desc.value = pick.dataset.partName || "";
  if (code) code.value = pick.dataset.partId || "";
  const box = card.querySelector(".line-part-suggest");
  if (box) box.replaceChildren();
}

function pickErpModel(event) {
  const part = event.target.closest("[data-part-id]");
  if (part) {
    event.preventDefault();
    applyErpPart(part);
    return;
  }
  const pick = event.target.closest("[data-erp-id]");
  if (!pick) return;
  event.preventDefault();
  applyErpModel(pick.dataset.erpId, pick.dataset.modelName || "");
}

document.addEventListener("pointerdown", pickErpModel);
document.addEventListener("click", pickErpModel);

function syncLineWarranty(card, on) {
  if (!card) return;
  if ((card.querySelector('input[name="line_type"]')?.value || "") === "promo") return;
  const wrap = card.querySelector(".line-amount-wrap");
  const amount = card.querySelector('input[name="amount"]');
  const pay = card.querySelector('input[name="payment_type"]');
  if (wrap) wrap.classList.toggle("is-warranty", on);
  if (amount) {
    if (on) amount.value = "0";
    amount.readOnly = on;
  }
  if (pay) pay.value = on ? "garanty" : "Cash";
  if (!on) {
    card.querySelectorAll(".line-pay-row button.chip").forEach((el) => {
      el.classList.toggle("active", el.dataset.value === "Cash");
      el.disabled = false;
    });
  }
}

function applyPromo(card) {
  if (!card) return;
  const select = card.querySelector('select[name="promo_id"]');
  const opt = select && select.selectedOptions[0];
  const desc = card.querySelector('input[name="description"]');
  const amount = card.querySelector('input[name="amount"]');
  const val = card.querySelector(".line-val-wrap input");
  const pay = card.querySelector('input[name="payment_type"]');
  if (opt && opt.value) {
    if (desc) desc.value = opt.dataset.name || "";
    if (amount) amount.value = opt.dataset.client || "0";
    if (val) val.value = opt.dataset.val || "0";
  }
  if (pay) pay.value = "promo";
  if (amount) amount.readOnly = true;
}

function syncLineKind(card) {
  if (!card) return;
  const kind = card.querySelector('input[name="line_type"]')?.value || "work";
  card.dataset.kind = kind;
  const amount = card.querySelector('input[name="amount"]');
  const pay = card.querySelector('input[name="payment_type"]');
  const desc = card.querySelector('input[name="description"]');
  const box = card.querySelector(".line-part-suggest");
  if (kind !== "part" && box) box.replaceChildren();
  if (kind === "promo") {
    const w = card.querySelector('input[name="is_warranty"]');
    if (w) w.value = "0";
    card.querySelector(".chip-line-warranty")?.classList.remove("active");
    applyPromo(card);
    return;
  }
  const locked = Boolean(card.closest(".is-locked"));
  const warrantyOn = card.querySelector('input[name="is_warranty"]')?.value === "1";
  if (amount) amount.readOnly = warrantyOn || locked;
  if (kind === "diagnostic") {
    const body = card.closest("#lines-body");
    const label = body?.dataset.diagnosticLabel || "";
    const price = body?.dataset.diagnosticPrice || "0";
    if (desc && !desc.value.trim()) desc.value = label;
    if (amount && (amount.value === "" || amount.value === "0" || amount.value === "0.00")) {
      amount.value = price;
    }
  }
  if (pay && pay.value === "promo") {
    pay.value = "Cash";
    card.querySelectorAll(".line-pay-row button.chip").forEach((el) => {
      el.classList.toggle("active", el.dataset.value === "Cash");
    });
  }
}

function fillClientName(name, force) {
  const nameInput = document.getElementById("new_client_name");
  if (!nameInput || !name) return;
  if (force || !nameInput.value.trim()) nameInput.value = name;
}

document.addEventListener("change", (event) => {
  const sel = event.target.closest('select[name="promo_id"]');
  if (sel) applyPromo(sel.closest("[data-line-card]"));
});

document.addEventListener("htmx:afterSwap", (event) => {
  const found = event.target && event.target.querySelector
    ? event.target.querySelector("[data-erp-name]")
    : null;
  if (found) fillClientName(found.dataset.erpName, false);
});

document.addEventListener("click", (event) => {
  const fillBtn = event.target.closest("[data-fill-name]");
  if (fillBtn) {
    fillClientName(fillBtn.dataset.fillName, true);
    return;
  }

  const chip = event.target.closest("button.chip");
  if (!chip || chip.disabled) return;

  const toggleRow = chip.closest(".chip-row[data-toggle]");
  if (toggleRow) {
    const input = toggleRow.querySelector('input[type="hidden"]');
    const on = !chip.classList.contains("active");
    chip.classList.toggle("active", on);
    if (input) input.value = on ? "1" : "0";
    if (toggleRow.dataset.toggle === "is_warranty") {
      syncLineWarranty(chip.closest("[data-line-card]"), on);
    }
    return;
  }

  const row = chip.closest(".chip-row");
  if (!row) return;
  row.querySelectorAll("button.chip").forEach((el) => el.classList.remove("active"));
  chip.classList.add("active");
  const input = row.querySelector('input[type="hidden"]');
  if (input) input.value = chip.dataset.value;
  if (input && input.name === "line_type") {
    syncLineKind(chip.closest("[data-line-card]"));
  }
  if (input && input.name === "kind") {
    const sub = document.getElementById("collection-subtype");
    if (sub) sub.hidden = input.value !== "collection";
  }
});
