(function () {
  function serialFromScan(raw) {
    var text = String(raw || "").trim();
    if (!text) return "";
    try {
      text = decodeURIComponent(text);
    } catch (e) {
      /* keep raw */
    }
    var lower = text.toLowerCase();
    if (lower.indexOf("://") >= 0 || lower.indexOf("www.") === 0 || (text.indexOf("?") >= 0 && text.indexOf("=") >= 0)) {
      try {
        var url = new URL(text.indexOf("://") >= 0 ? text : "https://" + text.replace(/^\/+/, ""));
        var keys = ["sn", "serial", "serial_number", "s"];
        for (var i = 0; i < keys.length; i++) {
          var v = url.searchParams.get(keys[i]);
          if (v && v.trim()) return v.trim();
        }
        var parts = url.pathname.replace(/\/+$/, "").split("/");
        var last = parts[parts.length - 1] || "";
        if (last && last.toLowerCase() !== "index.html" && last.toLowerCase() !== "scan") {
          return decodeURIComponent(last);
        }
      } catch (err) {
        /* fall through */
      }
    }
    if (lower.indexOf("sn:") === 0 || lower.indexOf("sn=") === 0) {
      return text.split(/[:=]/)[1].trim();
    }
    return text;
  }

  window.serialFromScan = serialFromScan;

  var modal = document.getElementById("scan-modal");
  var denied = document.getElementById("scan-denied");
  var serialInput = document.getElementById("new_machine_serial");
  var title = document.getElementById("scan-modal-title");
  var scanner = null;

  function stopScanner() {
    if (!scanner) return Promise.resolve();
    return scanner
      .stop()
      .catch(function () {})
      .then(function () {
        try {
          scanner.clear();
        } catch (e) {}
        scanner = null;
      });
  }

  function closeModal() {
    if (modal) modal.hidden = true;
    return stopScanner();
  }

  function onScanSuccess(decoded) {
    if (!serialInput) return;
    serialInput.value = serialFromScan(decoded);
    serialInput.dispatchEvent(new Event("scan-done", { bubbles: true }));
    closeModal();
  }

  function startScan(mode) {
    if (typeof Html5Qrcode === "undefined") {
      if (denied) denied.hidden = false;
      return;
    }
    if (!modal) return;
    if (denied) denied.hidden = true;
    if (title) {
      title.textContent = mode === "barcode" ? "Barcode" : "QR";
    }
    modal.hidden = false;
    stopScanner().then(function () {
      scanner = new Html5Qrcode("scan-reader");
      var formats =
        mode === "barcode"
          ? [
              Html5QrcodeSupportedFormats.CODE_128,
              Html5QrcodeSupportedFormats.CODE_39,
              Html5QrcodeSupportedFormats.EAN_13,
              Html5QrcodeSupportedFormats.EAN_8,
              Html5QrcodeSupportedFormats.UPC_A,
              Html5QrcodeSupportedFormats.UPC_E,
              Html5QrcodeSupportedFormats.ITF,
            ]
          : [Html5QrcodeSupportedFormats.QR_CODE];
      var config = { fps: 10, qrbox: { width: 250, height: 250 }, formatsToSupport: formats };
      scanner
        .start({ facingMode: "environment" }, config, onScanSuccess, function () {})
        .catch(function () {
          if (denied) denied.hidden = false;
          closeModal();
        });
    });
  }

  document.querySelectorAll("[data-scan-mode]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      startScan(btn.getAttribute("data-scan-mode") || "qr");
    });
  });
  var closeBtn = document.getElementById("scan-close");
  if (closeBtn) closeBtn.addEventListener("click", function () {
    closeModal();
  });
})();
