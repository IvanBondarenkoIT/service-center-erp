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

  var serialInput = document.getElementById("new_machine_serial");
  var fileInput = document.getElementById("scan-file-input");
  var scanBtn = document.getElementById("scan-camera-btn");
  var statusEl = document.getElementById("scan-status");
  var failedEl = document.getElementById("scan-failed");
  var hintEl = document.getElementById("scan-hint");

  var DETECTOR_FORMATS = [
    "qr_code",
    "data_matrix",
    "aztec",
    "pdf417",
    "code_128",
    "code_39",
    "ean_13",
    "ean_8",
    "upc_a",
    "upc_e",
    "itf",
  ];

  function setBusy(busy, message) {
    if (scanBtn) scanBtn.disabled = !!busy;
    if (statusEl) {
      if (busy && message) {
        statusEl.textContent = message;
        statusEl.hidden = false;
      } else {
        statusEl.hidden = true;
        statusEl.textContent = "";
      }
    }
    if (!busy && hintEl) hintEl.hidden = false;
    if (busy && hintEl) hintEl.hidden = true;
  }

  function showFailed(show) {
    if (failedEl) failedEl.hidden = !show;
  }

  function applySerial(raw) {
    if (!serialInput) return false;
    var sn = serialFromScan(raw);
    if (!sn) return false;
    serialInput.value = sn;
    serialInput.dispatchEvent(new Event("scan-done", { bubbles: true }));
    showFailed(false);
    return true;
  }

  function loadImageBitmap(file) {
    if (window.createImageBitmap) {
      return createImageBitmap(file);
    }
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        URL.revokeObjectURL(url);
        resolve(img);
      };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        reject(new Error("image_load"));
      };
      img.src = url;
    });
  }

  function decodeWithBarcodeDetector(file) {
    if (typeof BarcodeDetector === "undefined") {
      return Promise.resolve(null);
    }
    var detector;
    try {
      detector = new BarcodeDetector({ formats: DETECTOR_FORMATS });
    } catch (e) {
      try {
        detector = new BarcodeDetector();
      } catch (e2) {
        return Promise.resolve(null);
      }
    }
    return loadImageBitmap(file)
      .then(function (bitmap) {
        return detector.detect(bitmap).then(function (codes) {
          if (bitmap.close) bitmap.close();
          if (codes && codes.length && codes[0].rawValue) {
            return codes[0].rawValue;
          }
          return null;
        });
      })
      .catch(function () {
        return null;
      });
  }

  function decodeWithHtml5Qrcode(file) {
    if (typeof Html5Qrcode === "undefined") {
      return Promise.resolve(null);
    }
    var reader = new Html5Qrcode("scan-file-fallback");
    return reader
      .scanFile(file, true)
      .then(function (decoded) {
        try {
          reader.clear();
        } catch (e) {}
        return decoded || null;
      })
      .catch(function () {
        try {
          reader.clear();
        } catch (e) {}
        return null;
      });
  }

  function decodeFile(file) {
    var recognizing = (statusEl && statusEl.dataset.msg) || "…";
    setBusy(true, recognizing);
    showFailed(false);
    return decodeWithBarcodeDetector(file)
      .then(function (value) {
        if (value) return value;
        return decodeWithHtml5Qrcode(file);
      })
      .then(function (value) {
        setBusy(false);
        if (!applySerial(value)) {
          showFailed(true);
        }
      })
      .catch(function () {
        setBusy(false);
        showFailed(true);
      });
  }

  if (scanBtn && fileInput) {
    scanBtn.addEventListener("click", function () {
      showFailed(false);
      fileInput.value = "";
      fileInput.click();
    });
    fileInput.addEventListener("change", function () {
      var file = fileInput.files && fileInput.files[0];
      if (!file) return;
      decodeFile(file);
    });
  }
})();
