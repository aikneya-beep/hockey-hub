from __future__ import annotations


def topbar(active: str = "") -> str:
    items = [
        ("home", "/", "Главная"),
        ("big", "/big-hockey", "Большой хоккей"),
        ("mine", "/my-hockey", "Мой хоккей"),
    ]
    nav = "".join(
        f'<a class="{"active" if key == active else ""}" href="{href}">{label}</a>'
        for key, href, label in items
    )
    return (
        '<header class="hub-topbar">'
        '<a class="hub-brand" href="/">HOCKEY <span>HUB</span></a>'
        f'<nav class="hub-nav">{nav}</nav>'
        '</header>'
    )


COMMON_CSS = r'''
:root{
  --hub-bg:#07090c;
  --hub-surface:#0d1117;
  --hub-surface-2:#11161e;
  --hub-line:#252d38;
  --hub-line-soft:#1b222c;
  --hub-text:#f3f5f8;
  --hub-muted:#8994a4;
  --hub-silver:#c8d0da;
  --hub-silver-dim:#737e8e;
  --hub-blue:#416f9f;
  --hub-blue-bright:#5b8fc9;
  color-scheme:dark;
  font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}
*{box-sizing:border-box}
html{background:var(--hub-bg)}
body{margin:0;background:var(--hub-bg);color:var(--hub-text)}
a{color:inherit}
button,input,textarea,select{font:inherit}
.hub-shell{max-width:1180px;margin:auto;padding:0 22px 72px}
.hub-topbar{height:72px;display:grid;grid-template-columns:auto 1fr;gap:32px;align-items:center;border-bottom:1px solid var(--hub-line-soft)}
.hub-brand{font-weight:900;letter-spacing:.02em;font-size:19px;text-decoration:none;white-space:nowrap}
.hub-brand span{color:#4f73ff}
.hub-nav{display:flex;gap:26px;align-items:center}
.hub-nav a{position:relative;text-decoration:none;color:#8994a4;font-size:13px;white-space:nowrap}
.hub-nav a:hover,.hub-nav a.active{color:#fff}
.hub-nav a.active:after{content:"";position:absolute;left:0;right:0;bottom:-27px;height:2px;background:linear-gradient(90deg,#b8c1cc,#416f9f)}
.hub-eyebrow{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#737e8e}
.hub-section-head{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:14px}
.hub-section-head h2{margin:0;font-size:14px;letter-spacing:.01em}
.hub-section-head a{font-size:10px;text-decoration:none;color:#737e8e}
.hub-card{background:linear-gradient(180deg,#10151c,#0b0f14);border:1px solid var(--hub-line);border-radius:17px}
@media(max-width:760px){
  .hub-shell{padding:0 14px 54px}
  .hub-topbar{height:auto;padding-top:14px;grid-template-columns:1fr}
  .hub-nav{height:44px;overflow:auto;border-top:1px solid var(--hub-line-soft);padding-top:12px;gap:20px}
  .hub-nav a.active:after{bottom:-14px}
}
'''
