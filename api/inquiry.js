// 官网询盘接收：POST /api/inquiry（multipart 表单）
// 顺序：①附件存 Blob ②询盘记录存 Blob ③用 sales@ 发邮件到 sales@ + 163 ④把邮件结果写回记录
// 存下来或发出邮件任意一个成功，就返回 success；网页据此才记 Google Ads 转化。
import { FIELDS, PREFIX, json, saveFile, readJSON, sendInquiryMail, verifySmtp, safeName } from './_lib.js';

const MAX_FILE = 4 * 1024 * 1024; // Vercel 函数请求体上限约 4.5MB；更大的附件网页会转交 Google 备份

// 浏览器关了 JavaScript 时，表单会直接提交到这里（form action="/api/inquiry"）：
// 这种请求 Accept 里有 text/html，成功就跳回原页面显示「已发送」，失败给一个能用邮箱发送的页面，而不是一段 JSON。
// 网页里的 fetch 不带 text/html，照旧返回 JSON。
function reply(request, fd, obj, status = 200) {
  if (!(request.headers.get('accept') || '').includes('text/html')) return json(obj, status);
  if (obj.success) {
    const next = String((fd && fd.get('_next')) || '');
    const back = /^https:\/\/bilateral\.top\/[^\s]*$/.test(next) ? next : '/?sent=1#contact';
    return Response.redirect(new URL(back, request.url), 303);
  }
  const html = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<title>Inquiry not sent</title><body style="font-family:Arial,sans-serif;max-width:560px;margin:60px auto;padding:0 16px;line-height:1.7">' +
    '<h2>询盘没有发出 / Your inquiry could not be sent</h2>' +
    '<p>请直接发邮件给我们 / Please email us directly: <a href="mailto:sales@bilateral.top">sales@bilateral.top</a></p>' +
    '<p><a href="/#contact">← 返回 / Back</a></p></body>';
  return new Response(html, { status, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' } });
}

export async function POST(request) {
  let fd;
  try {
    fd = await request.formData();
  } catch (e) {
    return reply(request, null, { success: false, error: 'bad body' }, 400);
  }
  if (String(fd.get('_honey') || '')) return reply(request, fd, { success: true, saved: true, mailed: true, id: 'ignored' });

  const fields = {};
  for (const k of FIELDS) fields[k] = String(fd.get(k) || '').slice(0, 5000).trim();
  if (!fields.email && !fields['需求 Message']) return reply(request, fd, { success: false, error: 'empty' }, 400);

  // 询盘编号由网页生成（BLD-日期-随机码），访客重试或浏览器补发时编号不变，这里据此去重
  const now = new Date();
  let id = fields['询盘编号 ID'];
  if (!/^[A-Za-z0-9-]{6,40}$/.test(id)) {
    id = 'BLD-' + now.toISOString().slice(0, 10).replace(/-/g, '') + '-' + Math.random().toString(36).slice(2, 7).toUpperCase();
    fields['询盘编号 ID'] = id;
  }
  const base = PREFIX + id + '/';
  try {
    const old = await readJSON(base + 'record.json');
    if (old) return reply(request, fd, { success: true, saved: true, mailed: old.mail === '已发送', duplicate: true, id, fileSaved: !!old.file });
  } catch (e) {}
  const errors = [];
  const h = request.headers;

  // ① 附件
  let fileRec = null, attachment = null;
  const file = fd.get('attachment');
  if (file && typeof file === 'object' && file.size > 0) {
    if (file.size > MAX_FILE) {
      errors.push('file too large');
    } else {
      const name = safeName(file.name);
      try {
        const buf = Buffer.from(await file.arrayBuffer());
        const r = await saveFile(base + 'file/' + name, buf, file.type || 'application/octet-stream');
        fileRec = { name: file.name || name, size: file.size, type: file.type || '', pathname: r.pathname };
        attachment = { filename: file.name || name, content: buf, contentType: file.type || undefined };
      } catch (e) {
        errors.push('file: ' + e.message);
      }
    }
  }

  // ② 记录
  const rec = {
    id,
    createdAt: now.toISOString(),
    fields,
    file: fileRec,
    fileNote: String(fd.get('附件 Attachment') || '').slice(0, 500),
    country: h.get('x-vercel-ip-country') || '',
    city: decodeURIComponent(h.get('x-vercel-ip-city') || ''),
    ip: (h.get('x-forwarded-for') || '').split(',')[0].trim(),
    ua: (h.get('user-agent') || '').slice(0, 300),
    status: '新询盘',
    mail: '发送中',
    history: [],
  };
  let saved = false;
  try {
    await saveFile(base + 'record.json', JSON.stringify(rec), 'application/json');
    saved = true;
  } catch (e) {
    errors.push('save: ' + e.message);
  }

  // ③ 邮件
  let mailed = false;
  try {
    await sendInquiryMail(rec, attachment);
    mailed = true;
  } catch (e) {
    errors.push('mail: ' + e.message);
  }

  // ④ 邮件结果写回记录
  if (saved) {
    rec.mail = mailed ? '已发送' : '失败：' + (errors.find(x => x.startsWith('mail')) || '');
    try { await saveFile(base + 'record.json', JSON.stringify(rec), 'application/json'); } catch (e) {}
  }

  const ok = saved || mailed;
  if (errors.length) console.error('inquiry', id, errors.join(' | '));
  return reply(request, fd, { success: ok, saved, mailed, id, fileSaved: !!fileRec }, ok ? 200 : 500);
}

// 健康检查：GET /api/inquiry → {ok, blob, smtp}（外联脚本每小时检查一次用）
// 加 ?smtp=1 会真的登录一次 SMTP（不发信），结果 smtp_login；同一实例 10 分钟内复用结果，免得被刷接口时频繁登录邮箱。
let smtpCache = null;
const SMTP_CACHE_MS = 10 * 60 * 1000;

export async function GET(request) {
  const out = {
    ok: true,
    blob: !!(process.env.BLOB_READ_WRITE_TOKEN || process.env.BLOB_STORE_ID || process.env.BLD_FAKE_STORE_DIR),
    smtp: !!(process.env.SMTP_PASS || process.env.SMTP_INSECURE_TEST),
  };
  let want = false;
  try { want = new URL(request.url).searchParams.get('smtp') === '1'; } catch (e) {}
  if (want && out.smtp) {
    if (!smtpCache || Date.now() - smtpCache.at > SMTP_CACHE_MS) {
      try {
        await verifySmtp();
        smtpCache = { at: Date.now(), ok: true };
      } catch (e) {
        smtpCache = { at: Date.now(), ok: false, err: [e.code, e.responseCode].filter(Boolean).join(' ') || 'error' };
      }
    }
    out.smtp_login = smtpCache.ok;
    if (!smtpCache.ok) out.smtp_error = smtpCache.err;
  }
  return json(out);
}
