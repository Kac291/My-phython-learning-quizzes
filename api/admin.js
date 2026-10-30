// 询盘后台接口（需要后台密码，放在请求头 x-admin-key）
//   GET  /api/admin?action=list                  → 全部询盘（新的在前）
//   GET  /api/admin?action=file&id=…             → 下载该询盘的附件
//   POST /api/admin {action:'status', id, status, note} → 改跟进状态 / 备注
import { timingSafeEqual } from 'node:crypto';
import { PREFIX, STATUSES, json, readFile, readJSON, saveFile, listRecords } from './_lib.js';

function authed(request) {
  const want = process.env.ADMIN_PASSWORD || '';
  const got = request.headers.get('x-admin-key') || '';
  if (want.length < 6) return false;
  const a = Buffer.from(want), b = Buffer.from(got);
  return a.length === b.length && timingSafeEqual(a, b);
}

const validId = id => /^[0-9A-Za-z-]{10,40}$/.test(id || '');

export async function GET(request) {
  if (!authed(request)) return json({ error: 'unauthorized' }, 401);
  const url = new URL(request.url);
  const action = url.searchParams.get('action') || 'list';

  if (action === 'list') {
    const paths = await listRecords();
    const recs = (await Promise.all(paths.map(p => readJSON(p).catch(() => null)))).filter(Boolean);
    recs.sort((x, y) => (y.createdAt || '').localeCompare(x.createdAt || ''));
    return json({ inquiries: recs, statuses: STATUSES });
  }

  if (action === 'file') {
    const id = url.searchParams.get('id');
    if (!validId(id)) return json({ error: 'bad id' }, 400);
    const rec = await readJSON(PREFIX + id + '/record.json');
    if (!rec || !rec.file) return json({ error: 'no file' }, 404);
    const f = await readFile(rec.file.pathname);
    if (!f) return json({ error: 'file missing' }, 404);
    return new Response(f.body, {
      headers: {
        'content-type': rec.file.type || f.contentType || 'application/octet-stream',
        'content-disposition': "attachment; filename*=UTF-8''" + encodeURIComponent(rec.file.name),
        'cache-control': 'no-store',
      },
    });
  }
  return json({ error: 'bad action' }, 400);
}

export async function POST(request) {
  if (!authed(request)) return json({ error: 'unauthorized' }, 401);
  let body;
  try { body = await request.json(); } catch (e) { return json({ error: 'bad body' }, 400); }
  if (body.action !== 'status' || !validId(body.id)) return json({ error: 'bad request' }, 400);
  const p = PREFIX + body.id + '/record.json';
  const rec = await readJSON(p);
  if (!rec) return json({ error: 'not found' }, 404);
  const before = { status: rec.status, note: rec.note || '' };
  if (body.status != null) {
    if (!STATUSES.includes(body.status)) return json({ error: 'bad status' }, 400);
    rec.status = body.status;
  }
  if (body.note != null) rec.note = String(body.note).slice(0, 2000);
  rec.history = (rec.history || []).concat([{ at: new Date().toISOString(), from: before, to: { status: rec.status, note: rec.note || '' } }]).slice(-30);
  await saveFile(p, JSON.stringify(rec), 'application/json');
  return json({ ok: true, inquiry: rec });
}
