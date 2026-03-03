(() => {
  function createAppUiUtils(options = {}) {
    const getEl = typeof options.getEl === "function" ? options.getEl : (id) => document.getElementById(id);
    const $ = (id) => getEl(id);
    let toastTimer = null;

    function getFocusableTriggerEl() {
      const active = document.activeElement;
      if (!(active instanceof HTMLElement)) return null;
      if (!active.isConnected) return null;
      return active;
    }

    function focusIfPossible(el) {
      if (!(el instanceof HTMLElement)) return false;
      if (!el.isConnected) return false;
      if (el.matches(":disabled")) return false;
      try {
        el.focus();
        return document.activeElement === el;
      } catch {
        return false;
      }
    }

    function syncDialogOpenState() {
      const hasOpenDialog = !!document.querySelector("dialog[open]");
      document.body.classList.toggle("dialog-open", hasOpenDialog);
    }

    function prefersReducedMotion() {
      return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    }

    function isMobileLikeViewport() {
      return window.matchMedia("(max-width: 640px)").matches || window.matchMedia("(pointer: coarse)").matches;
    }

    function revealHintIfNeeded(el) {
      if (!(el instanceof HTMLElement)) return;
      if (!isMobileLikeViewport()) return;
      if (!String(el.textContent || "").trim()) return;
      const rect = el.getBoundingClientRect();
      const vh = window.innerHeight || document.documentElement.clientHeight || 0;
      if (!vh) return;
      const safeTop = 88;
      const safeBottom = 110;
      const outOfView = rect.top < safeTop || rect.bottom > vh - safeBottom;
      if (!outOfView) return;
      try {
        el.scrollIntoView({ block: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
      } catch {}
    }

    function isBusy(el) {
      return el?.getAttribute("aria-busy") === "true";
    }

    function toast(message, kind) {
      const el = $("toast");
      if (!el) return;
      if (!message) {
        el.classList.add("hidden");
        return;
      }
      el.textContent = message;
      el.className = `toast ${kind ?? ""}`.trim();
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => {
        el.classList.add("hidden");
      }, 2400);
    }

    function setButtonBusy(btn, busy, busyText) {
      if (!btn) return;
      if (busy) {
        btn.dataset.prevDisabled = String(btn.disabled);
        btn.dataset.prevText = btn.textContent || "";
        btn.disabled = true;
        btn.setAttribute("aria-busy", "true");
        if (busyText) btn.textContent = busyText;
      } else {
        btn.disabled = btn.dataset.prevDisabled === "true";
        btn.removeAttribute("aria-busy");
        if (btn.dataset.prevText != null) btn.textContent = btn.dataset.prevText;
        delete btn.dataset.prevDisabled;
        delete btn.dataset.prevText;
      }
    }

    function cloneDeep(obj) {
      return JSON.parse(JSON.stringify(obj));
    }

    function stableCopy(value) {
      if (Array.isArray(value)) return value.map(stableCopy);
      if (!value || typeof value !== "object") return value;
      const out = {};
      for (const key of Object.keys(value).sort()) {
        out[key] = stableCopy(value[key]);
      }
      return out;
    }

    function stableStringify(value) {
      return JSON.stringify(stableCopy(value));
    }

    return {
      getFocusableTriggerEl,
      focusIfPossible,
      syncDialogOpenState,
      prefersReducedMotion,
      isMobileLikeViewport,
      revealHintIfNeeded,
      isBusy,
      toast,
      setButtonBusy,
      cloneDeep,
      stableCopy,
      stableStringify,
    };
  }

  window.GRWAppUiUtils = {
    createAppUiUtils,
  };
})();
