/**
 * Ascentir Video Tracking Worker
 *
 * Handles two routes:
 *   GET /v/{lead_id}      → log view to KV, redirect to R2 landing page
 *   GET /api/views        → return all logged views as JSON (for dashboard sync)
 *
 * KV namespace binding:  VIEWS
 * Plain-text binding:    R2_PUBLIC_URL  (e.g. https://pub-xxx.r2.dev)
 *
 * Views are stored as individual keys: view:{lead_id}:{iso_timestamp}
 * Value: { leadId, ts, ip, ua }
 * TTL: 90 days
 */

const TTL_SECONDS = 60 * 60 * 24 * 90;   // 90 days

export default {
  async fetch(request, env) {
    const url   = new URL(request.url);
    const parts = url.pathname.split('/').filter(Boolean);

    // ── GET /v/{lead_id} ─────────────────────────────────────────────────────
    if (parts[0] === 'v' && parts[1]) {
      const leadId = parts[1];
      const ts     = new Date().toISOString();
      const ip     = request.headers.get('CF-Connecting-IP') || '';
      const ua     = request.headers.get('User-Agent') || '';

      // Ignore bot/prefetch traffic
      const isBot = /bot|crawl|fetch|preview|slack|telegram|whatsapp|facebookexternal/i.test(ua);
      if (!isBot) {
        const key = `view:${leadId}:${ts}`;
        await env.VIEWS.put(
          key,
          JSON.stringify({ leadId, ts, ip, ua: ua.slice(0, 120) }),
          { expirationTtl: TTL_SECONDS }
        );
      }

      const landingUrl = `${env.R2_PUBLIC_URL}/pages/${leadId}.html`;
      return Response.redirect(landingUrl, 302);
    }

    // ── GET /api/views ────────────────────────────────────────────────────────
    if (parts[0] === 'api' && parts[1] === 'views') {
      // Optional ?since=ISO_TIMESTAMP filter
      const since = url.searchParams.get('since');

      let cursor    = undefined;
      const results = [];

      do {
        const list = await env.VIEWS.list({ prefix: 'view:', cursor, limit: 1000 });
        for (const key of list.keys) {
          const val = await env.VIEWS.get(key.name, { type: 'json' });
          if (!val) continue;
          if (since && val.ts <= since) continue;
          results.push(val);
        }
        cursor = list.list_complete ? undefined : list.cursor;
      } while (cursor);

      return Response.json(results, {
        headers: { 'Access-Control-Allow-Origin': '*' }
      });
    }

    // ── GET /health ───────────────────────────────────────────────────────────
    if (parts[0] === 'health') {
      return Response.json({ ok: true, ts: new Date().toISOString() });
    }

    return new Response('Not found', { status: 404 });
  }
};
