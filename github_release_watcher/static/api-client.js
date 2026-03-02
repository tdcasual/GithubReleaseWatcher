(function attachApiClient(global) {
  class UnauthorizedError extends Error {
    constructor() {
      super("unauthorized");
      this.code = "unauthorized";
    }
  }

  const API = {
    async request(path, options) {
      const mergedHeaders = { Accept: "application/json", ...(options?.headers ?? {}) };
      const { headers: _ignored, ...rest } = options ?? {};
      const res = await fetch(`/api/v1${path}`, {
        credentials: "same-origin",
        ...rest,
        headers: mergedHeaders,
      });
      let data = {};
      try {
        data = await res.json();
      } catch {
        data = {};
      }
      if (res.status === 401 || data?.error === "unauthorized") throw new UnauthorizedError();
      return data;
    },
    async get(path) {
      return await API.request(path, { method: "GET" });
    },
    async post(path, body) {
      return await API.request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
      });
    },
    async put(path, body) {
      return await API.request(path, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
      });
    },
  };

  global.GRWApiClient = { API, UnauthorizedError };
})(window);
