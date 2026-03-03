(() => {
  function createAuthController(options = {}) {
    const getEl = typeof options.getEl === "function" ? options.getEl : (id) => document.getElementById(id);
    const apiGetMe = typeof options.apiGetMe === "function" ? options.apiGetMe : async () => ({ user: {} });
    const onAuthResolved = typeof options.onAuthResolved === "function" ? options.onAuthResolved : () => {};
    const syncDialogOpenState = typeof options.syncDialogOpenState === "function" ? options.syncDialogOpenState : () => {};

    const $ = (id) => getEl(id);
    let loginPromise = null;

    function startLoginFlow(message) {
      if (loginPromise) return loginPromise;
      loginPromise = new Promise((resolve) => {
        const dlg = $("loginDialog");
        $("loginError").textContent = message || "";
        $("loginUsername").value = "";
        $("loginPassword").value = "";
        dlg.showModal();
        syncDialogOpenState();
        setTimeout(() => $("loginUsername").focus(), 0);
        dlg.addEventListener(
          "cancel",
          (e) => {
            e.preventDefault();
          },
          { once: true }
        );

        const onDone = (username, mustChangePassword) => {
          onAuthResolved({ username, mustChangePassword });
          try {
            dlg.close();
          } catch {}
          $("loginForm").onsubmit = null;
          loginPromise = null;
          resolve();
        };

        $("loginForm").onsubmit = async (e) => {
          e.preventDefault();
          const username = ($("loginUsername").value || "").trim();
          const password = $("loginPassword").value || "";
          if (!username || !password) {
            $("loginError").textContent = "请输入账号与密码。";
            return;
          }
          try {
            const resp = await fetch("/api/v1/login", {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json", Accept: "application/json" },
              body: JSON.stringify({ username, password }),
            });
            const res = await resp.json().catch(() => ({}));
            if (!resp.ok || res.error) {
              if (res.error === "rate_limited" || resp.status === 429) {
                $("loginError").textContent = "登录过于频繁，请稍后再试。";
              } else {
                $("loginError").textContent = "账号或密码错误。";
              }
              return;
            }
            onDone(res.user?.username || username, !!res.user?.must_change_password);
          } catch (err) {
            $("loginError").textContent = String(err?.message || err);
          }
        };
      });
      return loginPromise;
    }

    async function requireLogin() {
      try {
        const me = await apiGetMe();
        onAuthResolved({
          username: me.user?.username || "admin",
          mustChangePassword: !!me.user?.must_change_password,
        });
        return;
      } catch (e) {
        if (e?.code !== "unauthorized") throw e;
      }
      await startLoginFlow();
    }

    return {
      startLoginFlow,
      requireLogin,
    };
  }

  window.GRWAppAuth = {
    createAuthController,
  };
})();
