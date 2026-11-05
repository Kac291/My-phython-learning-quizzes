// 询盘接口和后台共用的工具：存储（Vercel Blob，私有）+ 邮件（sales@ 的 SMTP）
// 以 _ 开头的文件不会被 Vercel 当成接口公开。
import nodemailer from 'nodemailer';
import { promises as fsp } from 'node:fs';
import path from 'node:path';

export const FIELDS = ['询盘编号 ID', '姓名 Name', '公司 Company', 'email', '电话 Phone', '意向 Interest', '需求 Message', '来源 Source', '页面 Page', '备注 Note'];
export const STATUSES = ['新询盘', '已回复', '报价中', '已成交', '无效/推销'];
export const PREFIX = 'inquiries/';
const ACCESS = process.env.BLOB_ACCESS || 'private';

export function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
  });
}

/* ---------------- 存储 ----------------
 * 线上用 Vercel Blob（私有）。BLD_FAKE_STORE_DIR 只在本地测试时设置，改用本地文件夹。 */
const FAKE = process.env.BLD_FAKE_STORE_DIR;
let blobMod = null;
async function blob() {
  if (!blobMod) blobMod = await import('@vercel/blob');
  return blobMod;
}

export async function saveFile(pathname, body, contentType) {
  if (FAKE) {
    const p = path.join(FAKE, pathname);
    await fsp.mkdir(path.dirname(p), { recursive: true });
    const buf = typeof body === 'string' ? body : Buffer.from(await new Response(body).arrayBuffer());
    await fsp.writeFile(p, buf);
    return { pathname };
  }
  const { put } = await blob();
  const r = await put(pathname, body, {
    access: ACCESS, contentType, addRandomSuffix: false, allowOverwrite: true,
  });
  return { pathname: r.pathname };
}

export async function readFile(pathname) {
  if (FAKE) {
    const p = path.join(FAKE, pathname);
    const buf = await fsp.readFile(p).catch(() => null);
    return buf ? { body: buf, contentType: 'application/octet-stream', size: buf.length } : null;
  }
  const { get } = await blob();
  const r = await get(pathname, { access: ACCESS, useCache: false });
  if (!r || r.statusCode !== 200) return null;
  return { body: r.stream, contentType: r.blob.contentType, size: r.blob.size };
}

export async function readJSON(pathname) {
  const r = await readFile(pathname);
  if (!r) return null;
  return JSON.parse(await new Response(r.body).text());
}

export async function listRecords() {
  if (FAKE) {
    const root = path.join(FAKE, PREFIX);
    const ids = await fsp.readdir(root).catch(() => []);
    return ids.map(id => PREFIX + id + '/record.json');
  }
  const { list } = await blob();
  const out = [];
  let cursor;
  do {
    const r = await list({ prefix: PREFIX, cursor, limit: 1000 });
    for (const b of r.blobs) if (b.pathname.endsWith('/record.json')) out.push(b.pathname);
    cursor = r.hasMore ? r.cursor : undefined;
  } while (cursor);
  return out;
}

/* ---------------- 邮件 ---------------- */
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function makeTransport() {
  const user = process.env.SMTP_USER || 'sales@bilateral.top';
  if (!process.env.SMTP_PASS && !process.env.SMTP_INSECURE_TEST) throw new Error('SMTP_PASS 未设置');
  const port = Number(process.env.SMTP_PORT || 465);
  return nodemailer.createTransport({
    host: process.env.SMTP_HOST || 'smtp.qiye.aliyun.com',
    port,
    secure: process.env.SMTP_SECURE ? process.env.SMTP_SECURE === 'true' : port === 465,
    auth: process.env.SMTP_PASS ? { user, pass: process.env.SMTP_PASS } : undefined,
    connectionTimeout: 10000, greetingTimeout: 10000, socketTimeout: 20000,
    tls: process.env.SMTP_INSECURE_TEST ? { rejectUnauthorized: false } : undefined,
  });
}

/* 健康检查用：真的登录一次 SMTP（不发信），密码改了、邮箱被限制都能查出来 */
export async function verifySmtp() {
  await makeTransport().verify();
}

export async function sendInquiryMail(rec, attachment) {
  const user = process.env.SMTP_USER || 'sales@bilateral.top';
  const transport = makeTransport();

  const f = rec.fields;
  const site = process.env.SITE_URL || 'https://bilateral.top';
  const rows = FIELDS.map(k => [k, f[k]]);
  rows.push(['国家/地区 Country', rec.country || '']);
  if (rec.file) rows.push(['附件 Attachment', rec.file.name + '（' + Math.round(rec.file.size / 1024) + ' KB' + (attachment ? '，已附在邮件里' : '，在询盘后台下载') + '）']);
  if (rec.fileNote) rows.push(['附件说明', rec.fileNote]);
  const shown = rows.filter(r => r[1]);

  const text = shown.map(r => r[0] + ': ' + r[1]).join('\n') + '\n\n询盘后台：' + site + '/admin/#' + rec.id;
  const html = '<table cellpadding="8" style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px">' +
    shown.map(r => '<tr><th align="left" style="border:1px solid #ddd;background:#f6f6f6;white-space:nowrap">' + esc(r[0]) +
      '</th><td style="border:1px solid #ddd">' + esc(r[1]).replace(/\n/g, '<br>') + '</td></tr>').join('') +
    '</table><p style="color:#888;font-size:12px">这条询盘已存进官网询盘后台：<a href="' + site + '/admin/#' + rec.id + '">' + site + '/admin/</a>。直接回复本邮件即回复客户。</p>';

  const msg = {
    from: { name: process.env.MAIL_FROM_NAME || 'Bilateral 官网询盘', address: user },
    to: process.env.MAIL_TO || 'sales@bilateral.top',
    cc: process.env.MAIL_CC === undefined ? '15316555536@163.com' : (process.env.MAIL_CC || undefined),
    subject: '【官网询盘】新客户询盘 New Website Inquiry',
    text, html,
  };
  if (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email || '')) msg.replyTo = f.email;
  if (attachment) msg.attachments = [attachment];
  await transport.sendMail(msg);
}

export function safeName(name) {
  return String(name || 'attachment').replace(/[\\/:*?"<>|#%\s]+/g, '_').slice(-120) || 'attachment';
}
