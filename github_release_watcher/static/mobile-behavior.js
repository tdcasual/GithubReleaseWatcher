(function attachMobileBehavior(global) {
  function createMobileBehaviorController(deps) {
    const getEl = deps.getEl;
    const prefersReducedMotion = deps.prefersReducedMotion;

    const setupMobileSectionNav = () => {
      const nav = document.querySelector(".mobile-nav");
      if (!nav) return;
      const links = Array.from(nav.querySelectorAll('.mobile-nav-item[href^="#"]'));
      if (!links.length) return;

      const items = links
        .map((link) => {
          const raw = String(link.getAttribute("href") || "");
          const id = raw.startsWith("#") ? raw.slice(1) : "";
          const section = id ? document.getElementById(id) : null;
          return section ? { id, section, link } : null;
        })
        .filter(Boolean);
      if (!items.length) return;
      items.sort((a, b) => a.section.offsetTop - b.section.offsetTop);

      const sectionScrollOffset = () => {
        const cssOffsetRaw = getComputedStyle(document.documentElement).getPropertyValue("--section-scroll-offset");
        const cssOffset = Number.parseFloat(cssOffsetRaw);
        if (Number.isFinite(cssOffset) && cssOffset > 0) return Math.ceil(cssOffset);
        const topbar = document.querySelector(".topbar");
        return Math.ceil((topbar?.getBoundingClientRect().height || 0) + 12);
      };

      const setActive = (id) => {
        for (const item of items) {
          const active = item.id === id;
          item.link.classList.toggle("active", active);
          if (active) item.link.setAttribute("aria-current", "page");
          else item.link.removeAttribute("aria-current");
        }
      };

      const scrollToSection = (id) => {
        const target = document.getElementById(id);
        if (!target) return;
        const targetY = window.scrollY + target.getBoundingClientRect().top - sectionScrollOffset();
        window.scrollTo({ top: Math.max(0, targetY), behavior: prefersReducedMotion() ? "auto" : "smooth" });
        if (history.replaceState) history.replaceState(null, "", `#${id}`);
      };

      for (const item of items) {
        item.link.addEventListener("click", (e) => {
          e.preventDefault();
          setActive(item.id);
          scrollToSection(item.id);
        });
      }

      let ticking = false;
      const updateByScroll = () => {
        ticking = false;
        const offset = sectionScrollOffset();
        const probeY = offset + 8;
        const hashId = (location.hash || "").replace(/^#/, "");
        if (hashId) {
          const hashItem = items.find((x) => x.id === hashId);
          if (hashItem) {
            const rect = hashItem.section.getBoundingClientRect();
            const vh = window.innerHeight || document.documentElement.clientHeight || 0;
            const hashVisibleTop = Math.max(offset + 64, vh * 0.55);
            if (rect.top <= hashVisibleTop && rect.bottom > Math.min(offset - 32, 0)) {
              setActive(hashItem.id);
              return;
            }
          }
        }
        let current = items[0];
        for (const item of items) {
          if (item.section.getBoundingClientRect().top <= probeY) current = item;
          else break;
        }
        setActive(current.id);
      };
      const requestUpdate = () => {
        if (ticking) return;
        ticking = true;
        window.requestAnimationFrame(updateByScroll);
      };

      window.addEventListener("scroll", requestUpdate, { passive: true });
      window.addEventListener("resize", requestUpdate);
      window.addEventListener("hashchange", () => {
        const id = (location.hash || "").replace(/^#/, "");
        if (!id) return;
        const item = items.find((x) => x.id === id);
        if (item) setActive(item.id);
      });

      const currentHashId = (location.hash || "").replace(/^#/, "");
      if (currentHashId) {
        const current = items.find((x) => x.id === currentHashId);
        if (current) setActive(current.id);
        else requestUpdate();
      } else {
        requestUpdate();
      }
    };

    const setupLogsScrollHint = () => {
      const logsEl = getEl("logs");
      const hintEl = document.querySelector(".logs-scroll-hint");
      if (!logsEl || !(hintEl instanceof HTMLElement)) return;

      const dismiss = () => {
        if (hintEl.classList.contains("hidden")) return;
        hintEl.classList.add("hidden");
      };

      logsEl.addEventListener(
        "scroll",
        () => {
          if (logsEl.scrollTop > 8) dismiss();
        },
        { passive: true }
      );
      logsEl.addEventListener(
        "touchmove",
        () => {
          dismiss();
        },
        { passive: true }
      );
      logsEl.addEventListener(
        "wheel",
        () => {
          dismiss();
        },
        { passive: true }
      );
    };

    return {
      setupLogsScrollHint,
      setupMobileSectionNav,
    };
  }

  global.GRWMobileBehavior = { createMobileBehaviorController };
})(window);
