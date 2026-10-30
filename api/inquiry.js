// 官网询盘接收：POST /api/inquiry（multipart 表单）
// 顺序：①附件存 Blob ②询盘记录存 Blob ③用 sales@ 发邮件到 sales@ + 163 ④把邮件结果写回记录
// 存下来或发出邮件任意一个成功，就返回 success；网页据此才记 Google Ads 转化。
import { FIELDS, PREFIX, json, saveFile, readJSON, sendInquiryMail, safeName } from './_lib.js';

const MAX_FILE = 4 * 1024 * 1024; // Vercel 函数请求体上限约 4.5MB；更大的附件网页会转交 Google 备份

export async function POST(request) {
  let fd;
  try {
    fd = await request.formData();
  } catch (e) {
    return json({ success: false, error: 'bad body' }, 400);
  }
  if (String(fd.get('_honey') || '')) return json({ success: true, saved: true, mailed: true, id: 'ignored' });

  const fields = {};
  for (const k of FIELDS) fields[k] = String(fd.get(k) || '').slice(0, 5000).trim();
  if (!fields.email && !fields['需求 Message']) return json({ success: false, error: 'empty' }, 400);

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
    if (old) return json({ success: true, saved: true, mailed: old.mail === '已发送', duplicate: true, id, fileSaved: !!old.file });
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
  return json({ success: ok, saved, mailed, id, fileSaved: !!fileRec }, ok ? 200 : 500);
}

// 健康检查：GET /api/inquiry → {ok:true}（外联脚本每小时检查一次用）
export async function GET() {
  return json({
    ok: true,
    blob: !!(process.env.BLOB_READ_WRITE_TOKEN || process.env.BLOB_STORE_ID || process.env.BLD_FAKE_STORE_DIR),
    smtp: !!(process.env.SMTP_PASS || process.env.SMTP_INSECURE_TEST),
  });
}
