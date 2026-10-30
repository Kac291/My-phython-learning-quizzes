/**
 * 百兰朵官网询盘接收（Google Apps Script）
 *
 * 作用：官网询盘的第二份记录 + 备用发信通道。
 *   - 平时：官网自己的接收程序（bilateral.top/api/inquiry）存记录、发邮件，
 *     同时把同一条询盘抄一份到这里的 Google 表格「官网询盘记录」（只记录，不重复发邮件）。
 *   - 官网接收程序出问题时：这里负责记录 + 发邮件到 sales@ 和 163，附件存 Google Drive「官网询盘附件」。
 *   - 同一询盘编号只记一次。
 *
 * 部署：
 *   1. 打开 https://script.google.com → 新建项目，项目名改成「官网询盘」
 *   2. 删掉编辑器里原有内容，把本文件整段粘贴进去，Ctrl+S 保存
 *   3. 上方函数下拉框选 setup → 点「运行」→ 按提示授权（会提示“未经验证的应用”，
 *      点「高级」→「转至官网询盘（不安全）」→ 允许）。
 *      运行完 sales@ 和 163 会各收到一封测试邮件，Drive 里会多出表格和附件文件夹。
 *   4. 右上角「部署」→「新建部署」→ 齿轮选「网页应用」
 *        执行身份：我
 *        谁可以访问：任何人
 *      → 部署 → 复制「网页应用 URL」（https://script.google.com/macros/s/……/exec）发给 Claude。
 *
 * 以后改了代码：「部署」→「管理部署」→ 铅笔 → 版本选「新版本」→ 部署（URL 不变）。
 */

const CONFIG = {
  TO: 'sales@bilateral.top',
  CC: '15316555536@163.com',
  SUBJECT: '【官网询盘】新客户询盘 New Website Inquiry',
  SENDER_NAME: 'Bilateral 官网询盘',
  SHEET_NAME: '官网询盘记录',
  FOLDER_NAME: '官网询盘附件',
};

// 表格列 = 官网表单的字段名（和 FormSubmit 邮件里的一致，外联脚本按这些名字解析）
const FIELDS = ['询盘编号 ID', '姓名 Name', '公司 Company', 'email', '电话 Phone', '意向 Interest', '需求 Message', '来源 Source', '页面 Page', '备注 Note'];
const HEADER = ['提交时间'].concat(FIELDS, ['附件', '邮件状态']);

function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.tryLock(15000);
  try {
    const d = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    if (d._honey) return json_({ success: true, mailed: true }); // 机器人填了隐藏字段，直接丢弃
    const f = d.fields || {};
    if (!String(f['email'] || '').trim() && !String(f['需求 Message'] || '').trim()) {
      return json_({ success: false, error: 'empty' });
    }

    // 同一编号已经记过（访客重试 / 浏览器补发），不重复记录、不重复发邮件
    const id = clean_(f['询盘编号 ID']);
    if (id) {
      const sh0 = getSheet_();
      const n = sh0.getLastRow();
      if (n > 1) {
        const from = Math.max(2, n - 499);
        const ids = sh0.getRange(from, 2, n - from + 1, 1).getValues().map(r => String(r[0]));
        if (ids.indexOf(id) >= 0) return json_({ success: true, mailed: true, duplicate: true });
      }
    }

    // 1. 附件存 Drive
    let blob = null, fileUrl = '';
    if (d.file && d.file.data) {
      blob = Utilities.newBlob(Utilities.base64Decode(d.file.data),
        d.file.type || 'application/octet-stream', d.file.name || 'attachment');
      const stamp = Utilities.formatDate(new Date(), 'Asia/Shanghai', 'yyyyMMdd-HHmmss');
      const saved = getFolder_().createFile(blob.copyBlob().setName(stamp + '_' + blob.getName()));
      fileUrl = saved.getUrl();
    }

    // 2. 先写表格（留底）
    const sh = getSheet_();
    sh.appendRow([new Date()].concat(FIELDS.map(k => clean_(f[k])), [fileUrl, '发送中']));
    const row = sh.getLastRow();
    const statusCell = sh.getRange(row, HEADER.length);

    // 官网自己的接收程序已经发过邮件时，这里只做备份记录（d.mail === false）
    if (d.mail === false) {
      statusCell.setValue('仅备份（官网已发邮件）');
      return json_({ success: true, mailed: true, backup: true, row: row });
    }

    // 3. 再发邮件
    let mailed = false;
    try {
      sendMail_(f, blob, fileUrl);
      mailed = true;
      statusCell.setValue('已发邮件');
    } catch (err) {
      statusCell.setValue('邮件失败：' + err);
    }
    return json_({ success: true, mailed: mailed, row: row });
  } catch (err) {
    return json_({ success: false, error: String(err) });
  } finally {
    try { lock.releaseLock(); } catch (e2) {}
  }
}

// GET：不带参数 → {ok:true}，用来检查服务是否在线；
//      ?action=list&key=查看密码 → 返回最近的询盘，给官网的「询盘记录」页面用
function doGet(e) {
  const p = (e && e.parameter) || {};
  if (p.action !== 'list') return json_({ ok: true });
  const key = PropertiesService.getScriptProperties().getProperty('ADMIN_KEY');
  if (!key || p.key !== key) {
    Utilities.sleep(800); // 减慢猜密码
    return json_({ success: false, error: 'bad key' });
  }
  const sh = getSheet_();
  const n = sh.getLastRow();
  if (n < 2) return json_({ success: true, header: HEADER, rows: [] });
  const limit = Math.min(Number(p.limit) || 500, 2000);
  const from = Math.max(2, n - limit + 1);
  const rows = sh.getRange(from, 1, n - from + 1, HEADER.length).getValues()
    .map(r => r.map(v => v instanceof Date ? v.toISOString() : v)).reverse();
  return json_({ success: true, header: HEADER, rows: rows, sheet: sh.getParent().getUrl() });
}

function sendMail_(f, blob, fileUrl) {
  const rows = FIELDS.concat(['附件 Attachment']).map(k => {
    const v = k === '附件 Attachment' ? (fileUrl ? (blob ? blob.getName() + '（已附在邮件里，Drive 备份：' + fileUrl + '）' : fileUrl) : '') : clean_(f[k]);
    return [k, v];
  }).filter(r => r[1]);

  const text = rows.map(r => r[0] + ': ' + r[1]).join('\n');
  const html = '<table cellpadding="8" style="border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px">' +
    rows.map(r => '<tr><th align="left" style="border:1px solid #ddd;background:#f6f6f6;white-space:nowrap">' + esc_(r[0]) +
      '</th><td style="border:1px solid #ddd">' + esc_(r[1]).replace(/\n/g, '<br>') + '</td></tr>').join('') +
    '</table><p style="color:#888;font-size:12px">询盘已同时记录在 Google 表格「' + CONFIG.SHEET_NAME + '」。直接回复本邮件即回复客户。</p>';

  const opt = {
    to: CONFIG.TO,
    cc: CONFIG.CC,
    subject: CONFIG.SUBJECT,
    body: text,
    htmlBody: html,
    name: CONFIG.SENDER_NAME,
  };
  const email = String(f['email'] || '').trim();
  if (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) opt.replyTo = email;
  if (blob && blob.getBytes().length < 20 * 1024 * 1024) opt.attachments = [blob];
  MailApp.sendEmail(opt);
}

function getSheet_() {
  const props = PropertiesService.getScriptProperties();
  let ss = null;
  const id = props.getProperty('SHEET_ID');
  if (id) { try { ss = SpreadsheetApp.openById(id); } catch (e) { ss = null; } }
  if (!ss) {
    ss = SpreadsheetApp.create(CONFIG.SHEET_NAME);
    props.setProperty('SHEET_ID', ss.getId());
  }
  const sh = ss.getSheets()[0];
  if (sh.getLastRow() === 0) sh.appendRow(HEADER);
  const head = sh.getRange(1, 1, 1, HEADER.length);
  if (head.getValues()[0].join('|') !== HEADER.join('|')) head.setValues([HEADER]); // 旧版表头自动更新
  sh.setFrozenRows(1);
  head.setFontWeight('bold');
  return sh;
}

function getFolder_() {
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty('FOLDER_ID');
  if (id) { try { return DriveApp.getFolderById(id); } catch (e) {} }
  const folder = DriveApp.createFolder(CONFIG.FOLDER_NAME);
  props.setProperty('FOLDER_ID', folder.getId());
  return folder;
}

function clean_(v) {
  return String(v == null ? '' : v).slice(0, 5000).trim();
}
function esc_(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function json_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

/** 部署前运行一次：完成授权，建好表格和文件夹，生成「询盘记录」页面的查看密码，并发一封测试邮件 */
function setup() {
  const sh = getSheet_();
  getFolder_();
  showAdminKey();
  const res = doPost({ postData: { contents: JSON.stringify({ fields: {
    '询盘编号 ID': 'TEST-SETUP', '姓名 Name': '测试 Test', '公司 Company': '百兰朵（测试）', 'email': CONFIG.TO,
    '需求 Message': '这是部署时的测试询盘，可以删掉这一行。', '来源 Source': 'setup', '页面 Page': 'Apps Script',
  } }) } });
  Logger.log(res.getContent());
  Logger.log('表格：' + sh.getParent().getUrl());
}

/** 查看（第一次运行时生成）官网「询盘记录」页面的查看密码，在下方「执行日志」里看 */
function showAdminKey() {
  const props = PropertiesService.getScriptProperties();
  let key = props.getProperty('ADMIN_KEY');
  if (!key) {
    key = Utilities.getUuid().replace(/-/g, '').slice(0, 16);
    props.setProperty('ADMIN_KEY', key);
  }
  Logger.log('询盘记录页面的查看密码：' + key);
  return key;
}

/** 想换密码时运行：生成新密码（旧的立即失效） */
function resetAdminKey() {
  PropertiesService.getScriptProperties().deleteProperty('ADMIN_KEY');
  return showAdminKey();
}
