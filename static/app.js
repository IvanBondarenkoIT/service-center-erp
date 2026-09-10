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
}

function syncLineWarranty(card, on) {
  if (!card) return;
  const wrap = card.querySelector(".line-amount-wrap");
  const amount = card.querySelector('input[name="amount"]');
  const pay = card.querySelector('input[name="payment_type"]');
  if (wrap) wrap.classList.toggle("is-warranty", on);
  if (amount) {
    if (on) amount.value = "0";
    amount.readOnly = on;
  }
  if (pay) pay.value = on ? "garanty" : "Cash";
}

document.addEventListener("click", (event) => {
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
  if (input && input.name === "kind") {
    const sub = document.getElementById("collection-subtype");
    if (sub) sub.hidden = input.value !== "collection";
  }
});
