#!/usr/bin/env python3
"""生成繁體中文靜態頁 tw/index.html（台灣用語）。

為什麼：原來的 /tw/ 只是一個殼，打開後才用 JS 把簡體首頁抓過來轉成繁體，
Google 抓取時把它當成首頁的重複頁，不單獨收錄（Search Console:
「重複網頁，Google 選擇的規範網頁與用戶指定的不同」）。
現在改成事先把繁體內容寫進 tw/index.html，Google 一抓就是完整的繁體頁。

用法：每次修改簡體首頁 index.html 之後，在網站資料夾裡執行一次
    python _tools/build_tw.py
再把 index.html 和 tw/index.html 一起推到 GitHub。

轉換表直接讀取 index.html 裡的 TW_PAIRS / TW_PHRASES，和頁面上「繁」按鈕的轉換一致，
只需要維護一份。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "index.html"
OUT = ROOT / "tw" / "index.html"

TW_TITLE = "上海百蘭朵電子科技 | 半導體陶瓷零組件 · OEM 料號對照(AMAT/NAURA/LAM/SPTS)"
TW_DESC = ("上海百蘭朵電子科技（2009 年成立）：半導體設備陶瓷零組件 OEM 同等替換件製造商。"
           "可依 AMAT、LAM、SPTS、NAURA 原廠料號查詢；氧化鋁、氮化鋁、碳化矽、氧化鋯、石英，每批附 COC 材質證明。")
TW_OG_TITLE = "半導體陶瓷零組件 · OEM 料號對照 | 上海百蘭朵電子科技"

HAN = re.compile(r"[一-鿿]")
SKIP_TAGS = ("script", "style", "noscript", "textarea")
CONV_ATTRS = ("placeholder", "title", "aria-label", "alt", "data-cap")


def load_tables(html):
    m = re.search(r"const TW_PAIRS='([^']*)'", html)
    if not m:
        sys.exit("找不到 TW_PAIRS，index.html 結構變了？")
    pairs = m.group(1)
    cmap = {pairs[i]: pairs[i + 1] for i in range(0, len(pairs) - 1, 2)}
    m = re.search(r"const TW_PHRASES=(\[.*?\]);", html)
    if not m:
        sys.exit("找不到 TW_PHRASES，index.html 結構變了？")
    phrases = json.loads(m.group(1).replace("'", '"'))
    return cmap, phrases


def make_conv(cmap, phrases):
    def conv(s):
        if not HAN.search(s):
            return s
        s = HAN.sub(lambda c: cmap.get(c.group(0), c.group(0)), s)
        for a, b in phrases:
            s = s.replace(a, b)
        return s
    return conv


TOKEN = re.compile(r"<!--.*?-->|<![^>]*>|</?[a-zA-Z][^>]*>", re.S)
ATTR = re.compile(r'(\s(%s)=")([^"]*)(")' % "|".join(re.escape(a) for a in CONV_ATTRS))


def convert_body(html, conv):
    """只轉換正文文字和少數屬性，不動 script/style 和 data-zh/data-en。"""
    out, pos, skip = [], 0, None
    for m in TOKEN.finditer(html):
        text = html[pos:m.start()]
        out.append(text if skip else conv(text))
        tag = m.group(0)
        name_m = re.match(r"</?([a-zA-Z][a-zA-Z0-9-]*)", tag)
        name = name_m.group(1).lower() if name_m else ""
        if skip:
            if tag.lower().startswith("</" + skip):
                skip = None
        elif tag.startswith("<") and not tag.startswith("</") and name in SKIP_TAGS:
            skip = name
        if not skip and not tag.startswith("<!") and name:
            tag = ATTR.sub(lambda a: a.group(1) + conv(a.group(3)) + a.group(4), tag)
        out.append(tag)
        pos = m.end()
    out.append(html[pos:] if skip else conv(html[pos:]))
    return "".join(out)


def must_sub(pattern, repl, s, what):
    new, n = re.subn(pattern, repl, s, count=1, flags=re.S)
    if n != 1:
        sys.exit("替換失敗：" + what)
    return new


LANG_NAV = """<script>
/* 繁體靜態頁：點「简 / EN」時跳到對應語言的網址，並回到同一區塊 */
(function(){var seg=document.getElementById('langSeg');if(!seg)return;
var ids=['about','materials','manufacturing','precision','works','oem-xref','clients','faq','contact'];
seg.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('button[data-l]');if(!b)return;
  var l=b.getAttribute('data-l');if(l==='tw')return;e.preventDefault();e.stopPropagation();
  try{localStorage.setItem('bld-lang',l);}catch(_){}
  try{var cur=null,off=0;for(var i=0;i<ids.length;i++){var s=document.getElementById(ids[i]);if(!s)continue;var t=s.getBoundingClientRect().top;if(t<=innerHeight*0.4){cur=ids[i];off=-t;}}
    if(cur)sessionStorage.setItem('bld-pos',JSON.stringify({id:cur,off:off,t:Date.now()}));}catch(_){}
  location.href=l==='en'?'/en/':'/';},true);
})();
</script>
"""


def main():
    src = SRC.read_text(encoding="utf-8")
    cmap, phrases = load_tables(src)
    conv = make_conv(cmap, phrases)

    head_end = src.index("</head>")
    head, body = src[:head_end], src[head_end:]

    # ---- head：網址、語言、標題 ----
    head = head.replace("zh-CN", "zh-TW")
    head = must_sub(r"<head>", '<head>\n<script>window.BLD_PAGE="tw";</script>', head, "BLD_PAGE")
    head = must_sub(r"<title>.*?</title>", "<title>%s</title>" % TW_TITLE, head, "title")
    head = must_sub(r'<meta name="description" content="[^"]*">',
                    '<meta name="description" content="%s">' % TW_DESC, head, "description")
    head = must_sub(r'<link rel="canonical" href="https://bilateral.top/">',
                    '<link rel="canonical" href="https://bilateral.top/tw/">', head, "canonical")
    head = must_sub(r'<meta property="og:url" content="https://bilateral.top/">',
                    '<meta property="og:url" content="https://bilateral.top/tw/">\n<meta property="og:locale" content="zh_TW">',
                    head, "og:url")
    head = must_sub(r'<meta property="og:title" content="[^"]*">',
                    '<meta property="og:title" content="%s">' % TW_OG_TITLE, head, "og:title")
    head = re.sub(r'(<meta property="og:description" content=")([^"]*)(")',
                  lambda m: m.group(1) + conv(m.group(2)) + m.group(3), head, count=1)
    head = re.sub(r'(<meta name="(?:keywords|twitter:title|twitter:description)" content=")([^"]*)(")',
                  lambda m: m.group(1) + conv(m.group(2)) + m.group(3), head)

    # ---- body：轉繁體 + 表單送出後回到繁體頁 ----
    body = body.replace("zh-CN", "zh-TW")
    body = body.replace("https://bilateral.top/?sent=1#contact", "https://bilateral.top/tw/?sent=1#contact")
    body = convert_body(body, conv)
    body = must_sub(r"</body>", LANG_NAV + "</body>", body, "</body>")

    html = head + body
    html = html.replace('<button type="button" data-l="zh" class="on">', '<button type="button" data-l="zh">', 1)
    html = html.replace('<button type="button" data-l="tw">', '<button type="button" data-l="tw" class="on">', 1)

    header = "<!-- 此檔案由 _tools/build_tw.py 從 index.html 自動生成，請勿直接修改 -->\n"
    first, rest = html.split("\n", 1)
    OUT.write_text(first + "\n" + header + rest, encoding="utf-8")
    print("已生成", OUT.relative_to(ROOT), f"({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
