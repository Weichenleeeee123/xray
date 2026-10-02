// Shared by the production worker. The upstream address stays on the server.
export async function proxyBackend(
  request: Request,
  backendUrl: string | undefined,
  fetchImpl: typeof fetch = fetch,
): Promise<Response | null> {
  const incoming = new URL(request.url);
  const report = incoming.pathname === '/xray' || incoming.pathname.startsWith('/xray/');
  const forwarded = report || ['/api', '/research-assets', '/demo'].some(
    (prefix) => incoming.pathname === prefix || incoming.pathname.startsWith(prefix + '/'),
  );
  if (!forwarded) return null;
  if (incoming.pathname === '/xray') {
    incoming.pathname = '/xray/';
    return Response.redirect(incoming.href, 308);
  }
  let upstream: URL;
  try {
    if (!backendUrl) throw new Error('missing upstream');
    upstream = new URL(backendUrl);
    if (!['http:', 'https:'].includes(upstream.protocol) || upstream.username || upstream.password)
      throw new Error('invalid upstream');
    if (upstream.origin === incoming.origin) throw new Error('proxy loop');
  } catch {
    return Response.json({ detail: '后端服务尚未正确配置，请设置 XRAY_BACKEND_URL' }, { status: 503 });
  }
  const prefix = upstream.pathname.replace(/\/$/, '');
  upstream.pathname = prefix + incoming.pathname;
  upstream.search = incoming.search;
  const forwardedRequest = new Request(upstream, request);
  forwardedRequest.headers.delete('host');
  forwardedRequest.headers.set('X-Forwarded-Host', incoming.host);
  forwardedRequest.headers.set('X-Forwarded-Proto', incoming.protocol.slice(0, -1));
  try {
    const response = await fetchImpl(forwardedRequest, { redirect: 'manual' });
    const headers = new Headers(response.headers);
    const location = headers.get('location');
    if (location) {
      const redirected = new URL(location, upstream);
      if (redirected.origin === upstream.origin && redirected.pathname.startsWith(prefix + '/')) {
        headers.set('location', redirected.pathname.slice(prefix.length) + redirected.search + redirected.hash);
      }
    }
    // Pass bodies through without buffering, including NDJSON and uploaded files.
    return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
  } catch {
    return Response.json({ detail: '暂时无法连接后端服务，请稍后重试' }, { status: 502 });
  }
}
