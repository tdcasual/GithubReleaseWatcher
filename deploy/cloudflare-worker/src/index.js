function unauthorized() {
  return new Response("Unauthorized", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Protected", charset="UTF-8"' },
  });
}

function checkBasicAuth(request, user, pass) {
  if (!user || !pass) return true;
  const header = request.headers.get("Authorization") || "";
  const [scheme, encoded] = header.split(" ");
  if (scheme !== "Basic" || !encoded) return false;
  let decoded = "";
  try {
    decoded = atob(encoded);
  } catch {
    return false;
  }
  const idx = decoded.indexOf(":");
  if (idx < 0) return false;
  const u = decoded.slice(0, idx);
  const p = decoded.slice(idx + 1);
  return u === user && p === pass;
}

export default {
  async fetch(request, env) {
    const upstreamBase = String(env.UPSTREAM || "").trim();
    if (!upstreamBase) return new Response("Missing UPSTREAM", { status: 500 });

    const incomingUrl = new URL(request.url);

    if (!checkBasicAuth(request, env.BASIC_AUTH_USER, env.BASIC_AUTH_PASS)) {
      return unauthorized();
    }

    const upstreamUrl = new URL(upstreamBase);
    upstreamUrl.pathname = incomingUrl.pathname;
    upstreamUrl.search = incomingUrl.search;

    const upstreamRequest = new Request(upstreamUrl.toString(), request);
    const headers = new Headers(upstreamRequest.headers);
    headers.set("X-Forwarded-Proto", incomingUrl.protocol.replace(":", ""));
    if (incomingUrl.host) headers.set("X-Forwarded-Host", incomingUrl.host);

    return fetch(new Request(upstreamRequest, { headers, redirect: "manual" }));
  },
};
