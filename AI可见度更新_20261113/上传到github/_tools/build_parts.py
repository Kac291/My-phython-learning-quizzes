#!/usr/bin/env python3
"""生成「件号独立页」和 sitemap.xml。

为什么：买家和 AI 助手是按件号来问的（例如「AMAT 0200-01009 有没有替代供应商」）。
首页那张 39 行的大表对搜索引擎和 AI 来说只是一页；一个件号一个网址、标题里就带件号，
才容易被直接搜到和引用。

生成内容（全部从简体首页 index.html 的件号表读取，只需要维护那一张表）：
    oem-parts/index.html                 中文件号目录
    oem-parts/<品牌-件号>/index.html      中文件号页
    en/oem-parts/index.html              英文件号目录
    en/oem-parts/<brand-partno>/index.html  英文件号页
    sitemap.xml                      首页 + 全部件号页

用法：在首页件号表里增删件号之后，在网站文件夹里依次执行
    python _tools/build_parts.py
    python _tools/build_tw.py
再把改动一起推到 GitHub。（英文首页 en/index.html 的件号表仍需手工同步。）

页面里的 Google 代码（GA4 + Google Ads）与首页一致；询价按钮跳回首页表单并带上件号，
询盘提交、广告转化仍然只在首页表单那一处发生。
"""
import datetime
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "index.html"
SITE = "https://bilateral.top"
TODAY = datetime.date.today().isoformat()

# 与首页保持一致的统一口径 —— 改这里，所有件号页一起变
FACTS = {
    "tol": "±0.02–0.1 mm",
    "flat": "1 μm",
    "hole": "0.1 mm",
    "lead_zh": "30–60 天（已做过的件号可适当提前）",
    "lead_en": "30–60 days (repeat parts can ship sooner)",
}

BRANDS = {
    "AMAT": {"zh": "AMAT 应用材料", "en": "AMAT (Applied Materials)", "short": "AMAT"},
    "NAURA": {"zh": "NAURA 北方华创", "en": "NAURA", "short": "NAURA"},
    "LAM": {"zh": "LAM 泛林", "en": "LAM Research", "short": "LAM"},
    "SPTS": {"zh": "SPTS", "en": "SPTS", "short": "SPTS"},
}

# 部件英文名 → 中文名（按顺序匹配，先长后短）；匹配不到就只显示英文原名
GLOSSARY = [
    ("Showerhead RF Isolator", "喷淋头射频绝缘件"), ("Cover Plate Heater", "加热器盖板"),
    ("Chamber Cover", "腔体盖板"), ("Cover Plate", "盖板"), ("Cover Ring", "盖环"),
    ("Preheat Ring", "预热环"), ("Deposition Ring", "沉积环"), ("Insulation Ring", "绝缘环"),
    ("Clamp Ring", "压环"), ("Focus Ring", "聚焦环"), ("Guard Ring", "保护环"),
    ("Isolation Plate", "隔离板"), ("Isolation Part", "隔离件"), ("Robot Arm Pad", "机械手垫片"),
    ("Robot Finger", "机械手指"), ("Blade", "机械手叶片"), ("Chuck Pin", "卡盘销"),
    ("Lift Pin", "顶针"), ("Nozzle", "喷嘴"), ("Dome", "陶瓷穹顶"), ("Collar", "腔体套环"),
    ("Shutter Disc", "挡片"), ("Shield", "防着板"), ("Feedthru", "馈通件"),
    ("Insulator", "绝缘件"), ("Electrode", "电极"), ("Spacer", "垫圈"), ("Seal", "密封件"),
    ("Connector", "连接件"),
]
PROC_ZH = [("Ion Implant", "离子注入"), ("ESC / Chuck", "静电卡盘"), ("Transfer", "传输"),
           ("Robot", "机械手"), ("Heater", "加热器"), ("Etch", "刻蚀")]

GTAG = """<!-- Google 代码：GA4 + Google Ads，与首页一致 -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-3X69MHYF3K"></script>
<script>
window.dataLayer=window.dataLayer||[];
function gtag(){dataLayer.push(arguments);}
gtag('js',new Date());
gtag('config','G-3X69MHYF3K');
gtag('config','AW-18467829651');
/* 点击统计：件号询价、邮箱、电话（事件名与首页相同） */
document.addEventListener('click',function(e){
  try{
    var a=e.target.closest('a'); if(!a) return;
    if(a.hasAttribute('data-pn')) gtag('event','part_inquire',{part_no:a.getAttribute('data-pn')});
    else if((a.getAttribute('href')||'').indexOf('mailto:')===0) gtag('event','email_click');
    else if((a.getAttribute('href')||'').indexOf('tel:')===0) gtag('event','phone_click');
  }catch(err){}
},true);
/* 询盘来源：和首页用同一个 bld_src，访客从这里点到首页表单时来源不丢 */
(function(){try{
  if(sessionStorage.getItem('bld_src')) return;
  var keys=['gclid','gbraid','wbraid','utm_source','utm_medium','utm_campaign','utm_term'];
  var q=new URLSearchParams(location.search);
  var hit=keys.filter(function(k){return q.get(k);}).map(function(k){return k+'='+q.get(k);}).join('; ');
  if(!hit){var ref='';try{ref=document.referrer?new URL(document.referrer).hostname:'';}catch(e){}
    if(ref&&ref!==location.hostname) hit='referrer='+ref;}
  if(hit) sessionStorage.setItem('bld_src',hit+'; landing='+location.pathname);
}catch(e){}})();
</script>"""

CSS = """
:root{--bg:#f3efe6;--bg2:#ebe6da;--ink:#191613;--ink-70:rgba(25,22,19,.84);--ink-50:rgba(25,22,19,.66);
--line:rgba(25,22,19,.16);--red:#b5301c;
--serif:'Noto Serif SC','Songti SC','SimSun',Georgia,serif;
--sans:'Noto Sans SC',-apple-system,'PingFang SC','Microsoft YaHei','Segoe UI',sans-serif;
--mono:'IBM Plex Mono','SF Mono',Consolas,Menlo,monospace}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.75;-webkit-font-smoothing:antialiased}
a{color:inherit}
.wrap{max-width:980px;margin:0 auto;padding:0 clamp(20px,5vw,48px)}
.top{border-bottom:1px solid var(--line)}
.top .wrap{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:18px;padding-bottom:18px}
.brand{text-decoration:none;font-family:var(--serif);font-weight:900;font-size:20px;letter-spacing:.06em}
.brand small{font-family:var(--mono);font-weight:400;font-size:11px;letter-spacing:.14em;color:var(--ink-50);margin-left:12px;text-transform:uppercase}
.top nav{display:flex;align-items:center;gap:20px;font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase}
.top nav a{text-decoration:none;color:var(--ink-70)}
.top nav a:hover{color:var(--red)}
.crumb{font-family:var(--mono);font-size:12px;letter-spacing:.06em;color:var(--ink-50);padding:26px 0 0}
.crumb a{text-decoration:none}.crumb a:hover{color:var(--red)}
h1{font-family:var(--serif);font-weight:900;font-size:clamp(28px,4.6vw,46px);line-height:1.25;letter-spacing:.01em;margin:18px 0 6px}
h1 .pn{font-family:var(--mono);font-weight:600;color:var(--red);white-space:nowrap}
.sub{font-family:var(--mono);font-size:13px;letter-spacing:.08em;color:var(--ink-50);text-transform:uppercase}
.lead{font-size:17px;color:var(--ink-70);max-width:780px;margin:22px 0 0}
h2{font-family:var(--serif);font-weight:600;font-size:22px;margin:52px 0 14px;padding-top:18px;border-top:1px solid var(--ink)}
table{width:100%;border-collapse:collapse;font-size:15px}
th,td{text-align:left;vertical-align:top;padding:12px 0;border-bottom:1px solid var(--line)}
th{width:34%;font-weight:400;color:var(--ink-50);padding-right:18px}
td{font-weight:500}
td.mono,.mono{font-family:var(--mono)}
.cta-row{display:flex;flex-wrap:wrap;align-items:center;gap:14px 22px;margin:30px 0 0}
.cta{display:inline-block;background:var(--red);color:#fff;text-decoration:none;padding:14px 26px;font-weight:500;letter-spacing:.04em}
.cta:hover{background:var(--ink)}
.cta-line{font-family:var(--mono);font-size:13px}
ol,ul{padding-left:1.3em}
li{margin:6px 0;color:var(--ink-70)}
.rel{list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:0 28px}
.rel li{margin:0;padding:10px 0;border-bottom:1px solid var(--line);font-size:14.5px}
.rel a{text-decoration:none}.rel a:hover{color:var(--red)}
.rel .mono{font-weight:600;margin-right:10px}
.grp th,.grp td{font-size:14.5px}
.grp td a{text-decoration:none;font-family:var(--mono);font-weight:600;color:var(--red)}
.grp td a:hover{text-decoration:underline}
.legal{font-size:12.5px;line-height:1.7;color:var(--ink-50);margin:44px 0 0;max-width:860px}
footer{margin-top:64px;border-top:1px solid var(--line);background:var(--bg2)}
footer .wrap{padding-top:28px;padding-bottom:34px;font-size:13.5px;color:var(--ink-70)}
footer b{font-family:var(--serif);font-size:16px}
footer a{text-decoration:none;border-bottom:1px dotted currentColor}
@media(max-width:640px){th{width:42%}.brand small{display:none}.top nav{gap:14px}}
"""

T = {
 "zh": {
  "lang": "zh-CN", "home": "/", "idx": "/oem-parts/", "brand": "百兰朵", "brand_small": "Bilateral Electronics",
  "nav_idx": "件号目录", "nav_inq": "询价", "other": "English", "crumb_home": "首页", "crumb_idx": "OEM 件号对照",
  "site": "上海百兰朵电子科技",
  "cta": "询价这个件号 →", "cta_idx": "发件号 / 图纸询价 →", "or_mail": "或发邮件至",
  "h_spec": "基本信息", "h_cap": "制造与交付", "h_how": "怎么询价", "h_rel": "{b} 其他可对照件号",
  "k": ["设备品牌", "原厂件号", "部件名称", "制程 / 机台", "供货方式", "材料"],
  "v_supply": "OEM 同等替换件，按订单定制生产，不备现货",
  "v_mat": "按与原厂件相同的材料与等级制造，报价时确认",
  "ck": ["加工公差", "平面度", "最小孔径", "常规交期", "随货文件", "质量体系", "制造商"],
  "cv_doc": "每批附材料合格证（COC）", "cv_q": "ISO 9001",
  "cv_mfr": "上海百兰朵电子科技有限公司（2009 年成立；宁波、萍乡生产基地）",
  "how": ["把件号 {pn}、数量和交期要求发给我们；有图纸或旧件照片更好。",
          "工程师评审后 24 小时内回复报价与交期。",
          "按订单生产，出货随批附材料合格证（COC）。"],
  "legal": "所有原厂品牌与件号均为各自所有者的商标，仅用于型号识别；上海百兰朵生产 OEM 兼容替换件，与原始设备制造商无隶属、授权或背书关系。",
  "foot": "半导体设备陶瓷与金属零部件 · OEM 同等替换件 · 按图定制",
  "addr": "浙江宁波前湾玉海东路 136 号 20 栋",
 },
 "en": {
  "lang": "en", "home": "/en/", "idx": "/en/oem-parts/", "brand": "Bilateral Electronics", "brand_small": "上海百兰朵",
  "nav_idx": "Part Index", "nav_inq": "Inquiry", "other": "中文", "crumb_home": "Home", "crumb_idx": "OEM Cross-Reference",
  "site": "Shanghai Bilateral Electronics",
  "cta": "Request a quote for this part →", "cta_idx": "Send a part number or drawing →", "or_mail": "or email",
  "h_spec": "Part details", "h_cap": "Manufacturing and delivery", "h_how": "How to order", "h_rel": "Other {b} part numbers we cross-reference",
  "k": ["OEM brand", "OEM part number", "Description", "Process / tool", "Supply type", "Material"],
  "v_supply": "OEM-equivalent replacement, made to order (not stocked)",
  "v_mat": "Same material and grade as the OEM part; confirmed at quotation",
  "ck": ["Machining tolerance", "Flatness", "Minimum hole diameter", "Standard lead time", "Documentation", "Quality system", "Manufacturer"],
  "cv_doc": "Certificate of Conformance (COC) with every lot", "cv_q": "ISO 9001",
  "cv_mfr": "Shanghai Bilateral Electronics Technology Co., Ltd. (founded 2009; plants in Ningbo and Pingxiang, China)",
  "how": ["Send us part number {pn}, the quantity and your required date. A drawing or photos of the used part help.",
          "Our engineers review it and reply with price and lead time within 24 hours.",
          "The part is made to order and ships with a Certificate of Conformance (COC)."],
  "legal": "All OEM brand names and part numbers are trademarks of their respective owners and are used for identification only. Shanghai Bilateral Electronics manufactures OEM-compatible replacement parts and is not affiliated with, authorized by, or endorsed by the original equipment manufacturers.",
  "foot": "Ceramic and metal parts for semiconductor equipment · OEM-equivalent replacements · custom parts to drawing",
  "addr": "Bldg 20, No.136 Yuhai East Rd, Qianwan, Ningbo, Zhejiang, China",
 },
}


def e(s):
    return html.escape(s, quote=True)


def slug(b, pn):
    return (b + "-" + pn).lower()


def zh_name(desc):
    for en_, zh_ in GLOSSARY:
        if en_.lower() in desc.lower():
            return zh_
    return ""


def zh_proc(proc):
    for en_, zh_ in PROC_ZH:
        proc = proc.replace(en_, zh_)
    return proc


def load_parts():
    src = SRC.read_text(encoding="utf-8")
    rows = re.findall(
        r'<div class="xref-row" data-b="([^"]+)"[^>]*>.*?<span class="xc-no">(?:<a [^>]*>)?([^<]+)(?:</a>)?</span>'
        r'<span class="xc-desc">([^<]*)</span><span class="xc-proc">([^<]*)</span>', src, flags=re.S)
    if not rows:
        sys.exit("首页里找不到件号表，index.html 结构变了？")
    parts = []
    for b, pn, desc, proc in rows:
        if b not in BRANDS:
            sys.exit("未知品牌 %s —— 请在 build_parts.py 的 BRANDS 里补上" % b)
        proc = html.unescape(proc).strip()
        parts.append({"b": b, "pn": html.unescape(pn).strip(), "desc": html.unescape(desc).strip(),
                      "proc": "" if proc in ("—", "-", "") else proc})
    seen = set()
    for p in parts:
        p["slug"] = slug(p["b"], p["pn"])
        if p["slug"] in seen:
            sys.exit("件号重复：" + p["slug"])
        seen.add(p["slug"])
    return parts


def head(lang, title, desc, path, alt_zh, alt_en, ld):
    t = T[lang]
    return f"""<!DOCTYPE html>
<!-- 此文件由 _tools/build_parts.py 自动生成，请勿直接修改 -->
<html lang="{t['lang']}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{SITE}{path}">
<link rel="alternate" hreflang="zh-Hans" href="{SITE}{alt_zh}">
<link rel="alternate" hreflang="en" href="{SITE}{alt_en}">
<link rel="alternate" hreflang="x-default" href="{SITE}{alt_en}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{e(t['site'])}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{SITE}{path}">
<style>{CSS}</style>
<script type="application/ld+json">
{json.dumps(ld, ensure_ascii=False, indent=1)}
</script>
{GTAG}
</head>
<body>
"""


def top(lang, other_href, inq_href, pn=None):
    t = T[lang]
    dp = f' data-pn="{e(pn)}"' if pn else ""
    return f"""<header class="top"><div class="wrap">
  <a class="brand" href="{t['home']}">{e(t['brand'])}<small>{e(t['brand_small'])}</small></a>
  <nav><a href="{t['idx']}">{e(t['nav_idx'])}</a><a href="{other_href}">{e(t['other'])}</a><a href="{inq_href}"{dp}>{e(t['nav_inq'])}</a></nav>
</div></header>
"""


def foot(lang):
    t = T[lang]
    return f"""<footer><div class="wrap">
  <p><b>{e(t['site'])}</b> — {e(t['foot'])}</p>
  <p><a href="mailto:sales@bilateral.top">sales@bilateral.top</a> · <a href="tel:+8615316555536">+86 153 1655 5536</a> · {e(t['addr'])}</p>
  <p>© 2009–{TODAY[:4]} Shanghai Bilateral Electronics Technology Co., Ltd. 上海百兰朵电子科技有限公司</p>
</div></footer>
</body>
</html>
"""


def org_ref():
    return {"@type": "Organization", "@id": SITE + "/#organization",
            "name": "Shanghai Bilateral Electronics Technology Co., Ltd.", "url": SITE + "/"}


def part_page(lang, p, parts):
    t = T[lang]
    B = BRANDS[p["b"]]
    bname = B[lang]
    pn, desc = p["pn"], p["desc"]
    path = f"{t['idx']}{p['slug']}/"
    alt_zh, alt_en = f"/oem-parts/{p['slug']}/", f"/en/oem-parts/{p['slug']}/"
    zn = zh_name(desc)
    if lang == "zh":
        proc = zh_proc(p["proc"])
        name = f"{desc}（{zn}）" if zn else desc
        title = f"{B['short']} {pn} 替换件 — {name} | 上海百兰朵"
        mdesc = (f"{bname} 原厂件号 {pn}（{name}）的 OEM 同等替换件，上海百兰朵按订单定制生产。"
                 f"加工公差 {FACTS['tol']}，平面度可达 {FACTS['flat']}，常规交期 30–60 天，每批附 COC。")
        h1 = f'{e(bname)} <span class="pn">{e(pn)}</span> 替换件'
        sub = e(name) + (f" · {e(proc)}" if proc else "")
        lead = (f"上海百兰朵电子科技为 {e(bname)} 原厂件号 <b>{e(pn)}</b>（{e(name)}）提供 OEM 同等替换件"
                + (f"，用于 {e(proc)} 制程设备" if proc else "")
                + "。按与原厂件相同的材料与等级、按订单定制生产，每批随附材料合格证（COC）。")
        cv = [FACTS["tol"] + "（视零件结构与材料而定）", "可达 " + FACTS["flat"], FACTS["hole"], FACTS["lead_zh"]]
        mail_sub = f"询价 {B['short']} {pn}"
    else:
        proc = p["proc"]
        name = desc
        title = f"{B['short']} {pn} Replacement — {desc} | Bilateral Electronics"
        mdesc = (f"OEM-equivalent replacement for {bname} part number {pn} ({desc}), made to order by Shanghai Bilateral Electronics. "
                 f"Tolerance {FACTS['tol']}, flatness to {FACTS['flat']}, lead time 30–60 days, COC with every lot.")
        h1 = f'{e(bname)} <span class="pn">{e(pn)}</span> replacement part'
        sub = e(desc) + (f" · {e(proc)}" if proc else "")
        lead = (f"Shanghai Bilateral Electronics manufactures an OEM-equivalent replacement for {e(bname)} part number <b>{e(pn)}</b> — {e(desc)}"
                + (f" — used on {e(proc)} equipment" if proc else "")
                + ". The part is made to order in China to the same material and grade as the original and ships with a Certificate of Conformance (COC).")
        cv = [FACTS["tol"] + " (depending on geometry and material)", "down to " + FACTS["flat"], FACTS["hole"], FACTS["lead_en"]]
        mail_sub = f"Inquiry {B['short']} {pn}"

    inq = f"{t['home']}?pn={quote(pn)}#contact"
    mailto = "mailto:sales@bilateral.top?subject=" + quote(mail_sub)
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": SITE + path, "url": SITE + path, "name": title, "description": mdesc,
         "inLanguage": t["lang"], "dateModified": TODAY,
         "isPartOf": {"@type": "WebSite", "@id": SITE + "/#website", "url": SITE + "/", "name": "Shanghai Bilateral Electronics / 上海百兰朵电子科技"},
         "publisher": org_ref(),
         "about": {"@type": "Thing", "name": f"Replacement for {B['en']} {pn} — {desc}",
                   "description": mdesc},
         "keywords": ", ".join(x for x in [pn, B["en"], desc, p["proc"], zn, "OEM-equivalent replacement part"] if x)},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": t["crumb_home"], "item": SITE + t["home"]},
            {"@type": "ListItem", "position": 2, "name": t["crumb_idx"], "item": SITE + t["idx"]},
            {"@type": "ListItem", "position": 3, "name": f"{B['short']} {pn}", "item": SITE + path}]}]}

    spec_vals = [e(bname), f'<span class="mono">{e(pn)}</span>', e(name), e(proc) if proc else None, e(t["v_supply"]), e(t["v_mat"])]
    spec = "".join(f"<tr><th>{e(k)}</th><td>{v}</td></tr>\n" for k, v in zip(t["k"], spec_vals) if v)
    cap_vals = cv + [t["cv_doc"], t["cv_q"], t["cv_mfr"]]
    cap = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>\n" for k, v in zip(t["ck"], cap_vals))
    how = "".join(f"<li>{e(x.format(pn=pn))}</li>\n" for x in t["how"])
    rel = [q for q in parts if q["b"] == p["b"] and q["slug"] != p["slug"]]
    rel_html = ""
    if rel:
        items = "".join(
            f'<li><a href="{t["idx"]}{q["slug"]}/"><span class="mono">{e(q["pn"])}</span>{e(q["desc"])}</a></li>\n' for q in rel)
        rel_html = f'<h2>{e(t["h_rel"].format(b=B["short"]))}</h2>\n<ul class="rel">\n{items}</ul>\n'
    other = alt_en if lang == "zh" else alt_zh

    return (head(lang, title, mdesc, path, alt_zh, alt_en, ld) + top(lang, other, inq, pn) + f"""<main class="wrap">
  <p class="crumb"><a href="{t['home']}">{e(t['crumb_home'])}</a> / <a href="{t['idx']}">{e(t['crumb_idx'])}</a> / {e(B['short'])} {e(pn)}</p>
  <h1>{h1}</h1>
  <p class="sub">{sub}</p>
  <p class="lead">{lead}</p>
  <div class="cta-row"><a class="cta" href="{inq}" data-pn="{e(pn)}">{e(t['cta'])}</a><span class="cta-line">{e(t['or_mail'])} <a href="{mailto}">sales@bilateral.top</a></span></div>

  <h2>{e(t['h_spec'])}</h2>
  <table>
{spec}  </table>

  <h2>{e(t['h_cap'])}</h2>
  <table>
{cap}  </table>

  <h2>{e(t['h_how'])}</h2>
  <ol>
{how}  </ol>
  <div class="cta-row"><a class="cta" href="{inq}" data-pn="{e(pn)}">{e(t['cta'])}</a></div>

  {rel_html}
  <p class="legal">{e(t['legal'])}</p>
</main>
""" + foot(lang))


def index_page(lang, parts):
    t = T[lang]
    path = t["idx"]
    n = len(parts)
    if lang == "zh":
        title = f"OEM 件号对照目录 — AMAT / NAURA 北方华创 / LAM / SPTS 替换件 | 上海百兰朵"
        mdesc = (f"上海百兰朵可对照的 {n} 个原厂件号目录：AMAT、NAURA 北方华创、LAM、SPTS 半导体设备陶瓷与金属零部件 OEM 同等替换件，"
                 "按订单定制，每批附 COC。")
        h1 = "OEM 件号对照目录"
        lead = (f"下面是上海百兰朵已对照的 {n} 个原厂件号，每个件号都有独立页面。表中只是部分件号——"
                "没找到的件号，把原厂件号、图纸或照片发给我们，工程师按图报价。")
        cols = ["原厂件号", "部件名称", "制程"]
    else:
        title = "OEM Part-Number Cross-Reference — AMAT, NAURA, LAM, SPTS Replacement Parts | Bilateral Electronics"
        mdesc = (f"Index of {n} OEM part numbers cross-referenced by Shanghai Bilateral Electronics: OEM-equivalent ceramic and metal replacement parts "
                 "for AMAT, NAURA, LAM and SPTS semiconductor equipment, made to order with COC.")
        h1 = "OEM part-number cross-reference"
        lead = (f"Shanghai Bilateral Electronics cross-references the {n} OEM part numbers below; each has its own page. "
                "This list is only a sample — if your part number is not here, send us the number, a drawing or a photo and our engineers will quote from it.")
        cols = ["OEM part no.", "Description", "Process"]
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "@id": SITE + path, "url": SITE + path, "name": title, "description": mdesc,
         "inLanguage": t["lang"], "dateModified": TODAY, "publisher": org_ref()},
        {"@type": "ItemList", "numberOfItems": n, "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": f"Replacement for {BRANDS[p['b']]['en']} {p['pn']} — {p['desc']}",
             "url": f"{SITE}{path}{p['slug']}/"} for i, p in enumerate(parts)]},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": t["crumb_home"], "item": SITE + t["home"]},
            {"@type": "ListItem", "position": 2, "name": t["crumb_idx"], "item": SITE + path}]}]}
    groups = ""
    for b in BRANDS:
        ps = [p for p in parts if p["b"] == b]
        if not ps:
            continue
        rows = ""
        for p in ps:
            zn = zh_name(p["desc"]) if lang == "zh" else ""
            name = f"{p['desc']}（{zn}）" if zn else p["desc"]
            proc = (zh_proc(p["proc"]) if lang == "zh" else p["proc"]) or "—"
            rows += f'<tr><td><a href="{path}{p["slug"]}/">{e(p["pn"])}</a></td><td>{e(name)}</td><td>{e(proc)}</td></tr>\n'
        groups += (f'<h2 id="{b.lower()}">{e(BRANDS[b][lang])} <span class="mono" style="font-size:14px;color:var(--ink-50)">· {len(ps)}</span></h2>\n'
                   f'<table class="grp"><thead><tr><th style="width:28%">{cols[0]}</th><th style="width:auto">{cols[1]}</th><th style="width:22%">{cols[2]}</th></tr></thead>\n<tbody>\n{rows}</tbody></table>\n')
    other = "/en/oem-parts/" if lang == "zh" else "/oem-parts/"
    inq = f"{t['home']}#contact"
    return (head(lang, title, mdesc, path, "/oem-parts/", "/en/oem-parts/", ld) + top(lang, other, inq) + f"""<main class="wrap">
  <p class="crumb"><a href="{t['home']}">{e(t['crumb_home'])}</a> / {e(t['crumb_idx'])}</p>
  <h1>{e(h1)}</h1>
  <p class="lead">{e(lead)}</p>
  <div class="cta-row"><a class="cta" href="{inq}">{e(t['cta_idx'])}</a><span class="cta-line">{e(t['or_mail'])} <a href="mailto:sales@bilateral.top">sales@bilateral.top</a></span></div>
{groups}
  <p class="legal">{e(t['legal'])}</p>
</main>
""" + foot(lang))


def sitemap(parts):
    def url(loc, alts, pri):
        x = "".join(f'    <xhtml:link rel="alternate" hreflang="{h}" href="{SITE}{u}"/>\n' for h, u in alts)
        return (f"  <url>\n    <loc>{SITE}{loc}</loc>\n{x}    <lastmod>{TODAY}</lastmod>\n"
                f"    <changefreq>monthly</changefreq>\n    <priority>{pri}</priority>\n  </url>\n")
    home_alts = [("zh-Hans", "/"), ("zh-Hant", "/tw/"), ("en", "/en/"), ("x-default", "/")]
    out = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n')
    out += url("/", home_alts, "1.0") + url("/en/", home_alts, "0.9") + url("/tw/", home_alts, "0.9")
    idx_alts = [("zh-Hans", "/oem-parts/"), ("en", "/en/oem-parts/"), ("x-default", "/en/oem-parts/")]
    out += url("/oem-parts/", idx_alts, "0.8") + url("/en/oem-parts/", idx_alts, "0.8")
    for p in parts:
        a = [("zh-Hans", f"/oem-parts/{p['slug']}/"), ("en", f"/en/oem-parts/{p['slug']}/"), ("x-default", f"/en/oem-parts/{p['slug']}/")]
        out += url(a[0][1], a, "0.7") + url(a[1][1], a, "0.7")
    return out + "</urlset>\n"


def main():
    parts = load_parts()
    n = 0
    for lang, base in (("zh", ROOT / "oem-parts"), ("en", ROOT / "en" / "oem-parts")):
        base.mkdir(parents=True, exist_ok=True)
        (base / "index.html").write_text(index_page(lang, parts), encoding="utf-8")
        n += 1
        for p in parts:
            d = base / p["slug"]
            d.mkdir(exist_ok=True)
            (d / "index.html").write_text(part_page(lang, p, parts), encoding="utf-8")
            n += 1
    (ROOT / "sitemap.xml").write_text(sitemap(parts), encoding="utf-8")
    print(f"已生成 {len(parts)} 个件号 × 中英文，共 {n} 个页面，并更新 sitemap.xml")


if __name__ == "__main__":
    main()
