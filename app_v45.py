from __future__ import annotations

import app_v44
import app_v05 as core

core.app.version = "0.45.0"

_old_home = core.render_page


def render_page_v45() -> str:
    page = _old_home().replace("v0.44", "v0.45", 1)
    page = page.replace(
        '<button class="icon-btn" id="spoilerToggle" type="button" title="Скрыть счёт">◉</button>',
        '<button class="spoiler-btn" id="spoilerToggle" type="button" title="Скрыть счёт"><span class="spoiler-icon">◉</span><span class="spoiler-label">Не спойлерить</span></button>',
        1,
    )
    css = r'''
.spoiler-btn{border:1px solid #2b3747;background:#101721;color:#dbe2eb;border-radius:10px;padding:9px 12px;display:inline-flex;align-items:center;gap:8px;cursor:pointer;font-size:12px;font-weight:700;white-space:nowrap;transition:border-color .15s ease,background .15s ease,color .15s ease}
.spoiler-btn:hover{border-color:#52627a;background:#131d2a}.spoiler-btn.spoiler-on{border-color:#6b7d96;background:#182231;color:#fff}.spoiler-icon{font-size:13px;line-height:1}.spoiler-label{line-height:1}
@media(max-width:560px){.spoiler-btn{padding:9px 10px;font-size:11px}}
'''
    page = page.replace("</style>", css + "</style>", 1)
    js = r'''
<script>
(function(){
  const spoilerBtn=document.getElementById('spoilerToggle');
  const label=spoilerBtn?.querySelector('.spoiler-label');
  if(!spoilerBtn||!label) return;
  const sync=()=>{const hidden=document.body.classList.contains('hide-scores');label.textContent=hidden?'Показать счёт':'Не спойлерить';spoilerBtn.setAttribute('aria-pressed',hidden?'true':'false');};
  sync();
  spoilerBtn.addEventListener('click',()=>requestAnimationFrame(sync));
})();
</script>
'''
    page = page.replace("</body>", js + "</body>", 1)
    return page


core.render_page = render_page_v45
app = core.app
