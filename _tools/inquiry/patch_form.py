#!/usr/bin/env python3
"""Patch inquiry form on index.html / en/index.html: site API primary, GAS backup (FormSubmit removed 2026-11),
mailto fallback, conversion only on confirmed delivery, source tracking."""
import re
import sys
from pathlib import Path

GAS_URL = sys.argv[2] if len(sys.argv) > 2 else ""

CSS = r"""
#fRefLine:has(b:empty){display:none}
.form-ok .f-lost{display:none;margin-top:14px;color:var(--red-bright);font-size:13.5px}
.form-fail{display:none;margin-top:22px;padding:20px 22px;border:1px solid var(--red-bright);border-radius:4px}
.form-fail.show{display:block}
.form-fail h4{font-family:var(--serif);font-weight:900;font-size:19px;letter-spacing:.04em}
.form-fail p{color:var(--ink-50);margin-top:10px;font-size:14px;line-height:1.7}
.form-fail .ff-act{display:flex;flex-wrap:wrap;gap:12px 22px;align-items:center;margin-top:16px}
.form-fail .ff-act a.mono{font-size:15px}
"""

BLDCONV = r"""window.bldConv=function(channel){
  try{
    gtag('event','generate_lead',{form:'inquiry',page_lang:document.documentElement.lang,inquiry_channel:channel||''});
    /* 只有询盘确认送达（官网后台或 Google 表格返回成功）才调用这里，Google Ads 转化 = 真实收到的询盘 */
    if(BLD_ADS.label){gtag('event','conversion',{send_to:BLD_ADS.id+'/'+BLD_ADS.label,transport_type:'beacon'});}
  }catch(e){}
};
"""

HIDDEN = ('<input type="hidden" name="来源 Source" id="fSrc" value="">'
          '<input type="hidden" name="页面 Page" id="fPage" value="">')

FAILBOX = r"""<div class="form-fail" id="formFail" role="alert">
            <h4 data-zh="网络问题，询盘没有发出" data-en="Your inquiry could not be sent">网络问题，询盘没有发出</h4>
            <p data-zh="很抱歉，表单暂时无法提交。您填写的内容还在，请点击下方按钮用邮箱直接发送（内容会自动带入），或稍后再试一次。" data-en="Sorry — our form could not be submitted due to a network issue. Your details are still here: click the button below to send them by email (pre-filled), or try again in a moment.">很抱歉，表单暂时无法提交。您填写的内容还在，请点击下方按钮用邮箱直接发送（内容会自动带入），或稍后再试一次。</p>
            <div class="ff-act">
              <a class="cta" id="failMail" href="mailto:sales@bilateral.top"><span data-zh="用邮箱发送" data-en="Send by email">用邮箱发送</span><span class="ar">→</span></a>
              <a class="mono" href="mailto:sales@bilateral.top">sales@bilateral.top</a>
              <a class="mono" href="tel:+8615316555536">+86 153 1655 5536</a>
            </div>
          </div>
          """

REFID = ('<span class="mono" id="fRefLine">REF <b id="fRefId"></b></span>')

LOST = ('<p class="f-lost" id="fLost" data-zh="附件未能随表单上传，请把图纸直接发到 sales@bilateral.top，我们收到后立即报价。" '
        'data-en="Your attachment could not be uploaded with the form — please email the drawing to sales@bilateral.top and we will quote right away.">'
        '附件未能随表单上传，请把图纸直接发到 sales@bilateral.top，我们收到后立即报价。</p>')

SUBMIT_JS = r"""/* 询盘发送（任何一步成功才算送达，才记 Google Ads 转化）：
   ① 官网自己的接收程序 /api/inquiry：存进官网询盘后台 + 用 sales@ 发邮件到 sales@ 和 163，
      同时抄一份到 Google 表格做第二份记录（只记录不重复发信）；
   ② ①不通 → Google 表格 + 邮件；
   ③ 都不通 → 存进访客浏览器的待发箱并提示用邮箱发送，访客下次打开本站时自动补发。
   每条询盘有唯一编号，重试/补发不会重复记录。 */
const BLD_FORM={api:'/api/inquiry',gas:'__GAS_URL__',apiMax:4*1024*1024};
let bldFileLost=false;
function bldTimeout(ms){const c=new AbortController();setTimeout(()=>c.abort(),ms);return c.signal;}
function bldFields(){const o={};for(const el of form.elements){if(!el.name||el.name[0]==='_'||el.type==='file')continue;o[el.name]=el.value;}return o;}
function bldNewId(){const d=new Date(),p=n=>String(n).padStart(2,'0');return 'BLD-'+d.getFullYear()+p(d.getMonth()+1)+p(d.getDate())+'-'+Math.random().toString(36).slice(2,6).toUpperCase();}
function bldFile64(f){return new Promise((ok,no)=>{const r=new FileReader();r.onload=()=>ok(String(r.result).split(',')[1]||'');r.onerror=()=>no(r.error);r.readAsDataURL(f);});}
async function bldSendAPI(fields,file,note){
  const fd=new FormData();
  for(const k in fields)fd.append(k,fields[k]);
  fd.append('_honey',(form.elements['_honey']||{}).value||'');
  if(file)fd.append('attachment',file,file.name);
  if(note)fd.append('附件 Attachment',note);
  const r=await fetch(BLD_FORM.api,{method:'POST',body:fd,signal:bldTimeout(file?60000:20000)});
  const j=await r.json();
  if(!j||j.success!==true)throw new Error('api '+r.status);
  return j;
}
async function bldSendGAS(fields,file,mail){
  if(!BLD_FORM.gas)throw new Error('gas not set');
  const p={fields,mail:mail!==false,_honey:(form.elements['_honey']||{}).value||''};
  if(file)p.file={name:file.name,type:file.type,data:await bldFile64(file)};
  const r=await fetch(BLD_FORM.gas,{method:'POST',body:JSON.stringify(p),keepalive:!file,signal:bldTimeout(file?60000:20000)});
  const j=await r.json();
  if(!j||j.success!==true)throw new Error('gas '+(j&&j.error));
  return j;
}
/* 依次尝试各通道，返回送达的通道名；都失败返回空字符串。附件没送到时 bldFileLost=true */
async function bldDeliver(fields,file){
  bldFileLost=false;
  const big=!!file&&file.size>BLD_FORM.apiMax;
  let a=null;
  try{a=await bldSendAPI(fields,big?null:file,big?'附件 '+file.name+' 较大（'+(file.size/1048576).toFixed(1)+' MB），已转存 Google Drive「官网询盘附件」':'');}catch(err){}
  if(a){
    const needMail=!a.mailed,needFile=!!file&&(big||!a.fileSaved);
    const g=bldSendGAS(fields,needFile?file:null,needMail);
    if(needMail||needFile){
      let ok=false;try{await g;ok=true;}catch(err){}
      if(!ok&&needFile)bldFileLost=true;
    }else g.catch(()=>{});
    return 'site';
  }
  try{
    const j=await bldSendGAS(fields,file,true);
    return 'sheet';
  }catch(err){}
  return '';
}
/* 待发箱：两条通道都失败的询盘先存在访客浏览器里 */
const BLD_OUTBOX='bld_outbox';
function bldOutbox(){try{return JSON.parse(localStorage.getItem(BLD_OUTBOX)||'[]')||[];}catch(e){return [];}}
function bldOutboxSave(list){try{list.length?localStorage.setItem(BLD_OUTBOX,JSON.stringify(list.slice(-10))):localStorage.removeItem(BLD_OUTBOX);}catch(e){}}
async function bldFlushOutbox(){
  const list=bldOutbox();if(!list.length)return;
  const left=[];
  for(const it of list){
    if(Date.now()-it.t>30*864e5)continue;            /* 超过 30 天的不再重发 */
    const f=Object.assign({},it.fields);
    f['备注 Note']='访客当时提交失败，本条为 '+new Date(it.t).toISOString().slice(0,16).replace('T',' ')+' UTC 的询盘，再次打开网站时自动补发';
    const ch=await bldDeliver(f,null);
    if(ch)bldConv('retry-'+ch);else left.push(it);
  }
  bldOutboxSave(left);
}
function bldMailto(fields){
  const sub='【官网询盘】Inquiry '+(fields['询盘编号 ID']||'')+' - '+(fields['姓名 Name']||'')+(fields['公司 Company']?' / '+fields['公司 Company']:'');
  let body=Object.keys(fields).filter(k=>fields[k]&&k!=='页面 Page').map(k=>k+': '+fields[k]).join('\n');
  if(body.length>1500)body=body.slice(0,1500)+'…';
  return 'mailto:sales@bilateral.top?subject='+encodeURIComponent(sub)+'&body='+encodeURIComponent(body);
}
const failBox=document.getElementById('formFail');
let bldPendingId='';
form.addEventListener('submit',async e=>{
 e.preventDefault();
 if(btn.disabled)return;
 let firstBad=null;
 fRules.forEach(([id,fn,msg])=>{const el=document.getElementById(id);if(fn(el.value))fClear(el);else{fErr(el,lang==='zh'?msg.zh:msg.en);if(!firstBad)firstBad=el;}});
 if(firstBad){firstBad.focus();firstBad.scrollIntoView({behavior:'smooth',block:'center'});return;}
 const fFile=document.getElementById('fFile');
 const file=fFile&&fFile.files&&fFile.files.length>0?fFile.files[0]:null;
 if(file&&file.size>10*1024*1024){fErr(fFile,lang==='zh'?'文件超过 10MB，请压缩后再传，或直接发邮件至 sales@bilateral.top':'File exceeds 10 MB — please zip it or email sales@bilateral.top');fFile.scrollIntoView({behavior:'smooth',block:'center'});return;}
 const btnTx=btn.querySelector('span'),btnOld=btnTx.textContent;
 btn.disabled=true;failBox.classList.remove('show');
 btnTx.textContent=lang==='zh'?'发送中…':'Sending…';
 const fields=bldFields();
 /* 同一份内容重试时沿用同一个编号，表格里不会重复 */
 if(!bldPendingId)bldPendingId=bldNewId();
 fields['询盘编号 ID']=bldPendingId;
 const channel=await bldDeliver(fields,file);
 const box=bldOutbox().filter(it=>it.fields['询盘编号 ID']!==bldPendingId);
 if(channel){
  bldOutboxSave(box);
  bldConv(channel);
  const lost=document.getElementById('fLost');if(lost)lost.style.display=bldFileLost?'block':'none';
  const rid=document.getElementById('fRefId');if(rid)rid.textContent=bldPendingId;
  bldPendingId='';
  form.style.display='none';okBox.classList.add('show');showOk();
 }else{
  box.push({t:Date.now(),fields});bldOutboxSave(box);
  try{gtag('event','inquiry_failed',{page_lang:document.documentElement.lang});}catch(err){}
  document.getElementById('failMail').href=bldMailto(fields);
  failBox.classList.add('show');failBox.scrollIntoView({behavior:'smooth',block:'center'});
  btn.disabled=false;btnTx.textContent=btnOld;
 }
});
/* 打开页面 3 秒后，静默补发待发箱里的询盘 */
setTimeout(()=>{bldFlushOutbox().catch(()=>{});},3000);
/* 询盘来源：记录广告点击 ID / utm / 来路，随询盘一起发出 */
(function(){
  const keys=['gclid','gbraid','wbraid','utm_source','utm_medium','utm_campaign','utm_term'];
  let src='';
  try{
    const q=new URLSearchParams(location.search);
    const hit=keys.filter(k=>q.get(k)).map(k=>k+'='+q.get(k)).join('; ');
    if(hit){src=hit;sessionStorage.setItem('bld_src',hit);}
    else src=sessionStorage.getItem('bld_src')||'';
    if(!src){
      let ref='';try{ref=document.referrer?new URL(document.referrer).hostname:'';}catch(e){}
      if(ref&&ref!==location.hostname){src='referrer='+ref;sessionStorage.setItem('bld_src',src);}
    }
  }catch(e){}
  const s=document.getElementById('fSrc'),pg=document.getElementById('fPage');
  if(s)s.value=src||'direct';
  if(pg)pg.value=location.pathname;
})();
"""


def to_en(frag):
    return re.sub(r'(data-en="([^"]*)">)[^<]*<', lambda m: m.group(1) + m.group(2) + "<", frag)


def patch(path: Path):
    is_en = path.parent.name == "en"
    failbox = to_en(FAILBOX) if is_en else FAILBOX
    lost = to_en(LOST) if is_en else LOST
    h = path.read_text(encoding="utf-8")
    n0 = len(h)

    def sub1(pattern, repl, flags=re.S):
        nonlocal h
        new, k = re.subn(pattern, lambda m: repl(m) if callable(repl) else repl, h, count=1, flags=flags)
        if k != 1:
            sys.exit(f"{path}: pattern not found: {pattern[:60]}")
        h = new

    # CSS
    sub1(r"(\.form-ok \.mono\{[^}]*\}\n)", lambda m: m.group(1) + CSS.lstrip("\n"))
    # bldConv
    sub1(r"window\.bldConv=function\(programmatic\)\{.*?\n\};\n", BLDCONV)
    # hidden source fields after honeypot
    sub1(r"(<input[^>]*name=\"_honey\"[^>]*>)", lambda m: m.group(1) + "\n" + HIDDEN)
    # fail box before success box
    sub1(r"(<div class=\"form-ok\" id=\"formOk\">)", lambda m: failbox + m.group(1))
    # attachment-lost note inside success box, after its mono line
    sub1(r"(<div class=\"form-ok\" id=\"formOk\">.*?<span class=\"mono\">INQUIRY LOGGED[^<]*</span>)",
         lambda m: m.group(1) + "\n" + REFID + "\n" + lost)
    # submit handler
    js = SUBMIT_JS.replace("__GAS_URL__", GAS_URL)
    sub1(r"form\.addEventListener\('submit',async e=>\{.*?\n\}\);\n(?=\(function\(\)\{const ff=)", js)
    # 繁体转换表补上新文案里缺的字
    m = re.search(r"const TW_PAIRS='([^']*)'", h)
    if m:
        pairs = m.group(1)
        have = {pairs[i] for i in range(0, len(pairs) - 1, 2)}
        add = "".join(a + b for a, b in ("络絡", "暂暫", "钮鈕") if a not in have)
        if add:
            h = h.replace("const TW_PAIRS='", "const TW_PAIRS='" + add, 1)
    path.write_text(h, encoding="utf-8")
    print(f"{path}: {n0} -> {len(h)}")


if __name__ == "__main__":
    root = Path(sys.argv[1])
    for p in (root / "index.html", root / "en" / "index.html"):
        patch(p)
