// Runtime proxy for all dashboard API calls.
//
// Rewrites in next.config.mjs are baked into the production build, which meant
// a dev-time/default API_BACKEND_URL could survive into `next start`. Reading
// the environment here keeps the bot-launched dashboard pointed at the bot's
// actual WEB_PORT every time.

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "proxy-connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "te",
  "trailer",
  "host",
  // fetch() transparently decompresses responses, so these must be recalculated.
  "content-length",
  "content-encoding",
]);

function backendBase(): string {
  return (process.env.API_BACKEND_URL || "http://127.0.0.1:8080").replace(/\/+$/, "");
}

function cleanHeaders(source: Headers): Headers {
  const result = new Headers();
  source.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      result.set(key, value);
    }
  });
  return result;
}

function errorResponse(status: number, message: string): Response {
  return new Response(
    JSON.stringify({ ok: false, message }),
    {
      status,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
      },
    }
  );
}

async function proxy(request: Request): Promise<Response> {
  const requestUrl = new URL(request.url);
  const suffix = requestUrl.pathname.startsWith("/api/")
    ? requestUrl.pathname.slice("/api/".length)
    : "";
  const apiPath = suffix ? `/api/${suffix}` : "/api";
  const target = `${backendBase()}${apiPath}${requestUrl.search}`;

  const headers = cleanHeaders(request.headers);
  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
    cache: "no-store",
  };
  if (!["GET", "HEAD"].includes(request.method.toUpperCase())) {
    init.body = await request.arrayBuffer();
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return errorResponse(502, `Dashboard proxy could not reach the bot API at ${backendBase()}: ${detail}`);
  }

  const responseHeaders = cleanHeaders(upstream.headers);
  responseHeaders.set("Cache-Control", "no-store");
  if (!responseHeaders.has("Access-Control-Allow-Origin")) {
    responseHeaders.set("Access-Control-Allow-Origin", "*");
  }
  const rawBody = await upstream.arrayBuffer();
  // 204/205/304 (and HEAD replies) must not carry a body, or Response throws.
  const nullBody = ["HEAD"].includes(request.method.toUpperCase()) ||
    [204, 205, 304].includes(upstream.status);
  const body = nullBody ? null : new Uint8Array(rawBody);
  return new Response(body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
  proxy as OPTIONS,
  proxy as HEAD,
};
