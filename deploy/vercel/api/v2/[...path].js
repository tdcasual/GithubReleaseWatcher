function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function normalizeUpstream(raw) {
  const base = String(raw || "").trim();
  if (!base) return null;
  return base.endsWith("/") ? base.slice(0, -1) : base;
}

module.exports = async (req, res) => {
  const upstreamBase = normalizeUpstream(process.env.UPSTREAM);
  if (!upstreamBase) {
    res.statusCode = 500;
    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    res.end("Missing UPSTREAM env var");
    return;
  }

  const host = req.headers.host || "localhost";
  const incomingUrl = new URL(req.url || "/", `https://${host}`);
  const pathParts = Array.isArray(req.query?.path) ? req.query.path : [req.query?.path].filter(Boolean);
  const restPath = pathParts.length ? `/${pathParts.join("/")}` : "";

  const upstreamUrl = new URL(upstreamBase);
  upstreamUrl.pathname = `${upstreamUrl.pathname.replace(/\/$/, "")}/api/v2${restPath}`;
  upstreamUrl.search = incomingUrl.search;

  const headers = new Headers();
  const skipHeaders = new Set(["host", "connection", "content-length", "accept-encoding"]);
  for (const [key, value] of Object.entries(req.headers || {})) {
    if (value == null) continue;
    if (skipHeaders.has(String(key).toLowerCase())) continue;
    if (Array.isArray(value)) headers.set(key, value.join(","));
    else headers.set(key, String(value));
  }
  if (!headers.has("x-forwarded-proto")) headers.set("x-forwarded-proto", "https");
  if (!headers.has("x-forwarded-host") && host) headers.set("x-forwarded-host", host);

  let body = undefined;
  const method = String(req.method || "GET").toUpperCase();
  if (!["GET", "HEAD"].includes(method)) {
    const buf = await readBody(req);
    body = buf.length ? buf : undefined;
  }

  const upstreamResp = await fetch(upstreamUrl.toString(), {
    method,
    headers,
    body,
    redirect: "manual",
  });

  res.statusCode = upstreamResp.status;

  const setCookie = upstreamResp.headers.getSetCookie?.();
  if (setCookie && setCookie.length) {
    res.setHeader("set-cookie", setCookie);
  }

  upstreamResp.headers.forEach((value, key) => {
    if (key.toLowerCase() === "set-cookie") return;
    res.setHeader(key, value);
  });

  const arr = await upstreamResp.arrayBuffer();
  res.end(Buffer.from(arr));
};
