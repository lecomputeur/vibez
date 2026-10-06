/* Bundled page-only capture. This script never receives native IPC privileges. */
(() => {
  'use strict';
  const config = __VIBEZ_CAPTURE_CONFIG__;
  window.__vibezCapture?.cancel?.();
  const state = { id: config.id, result: '', cancel: null };
  window.__vibezCapture = state;
  let settled = false, cleanupSelection = () => {}, restorePage = () => {};
  let fullGeometry = null;
  const finish = payload => {
    if (settled) return;
    settled = true;
    clearTimeout(timer);
    cleanupSelection();
    restorePage();
    window.removeEventListener('pagehide', onPageHide);
    if (window.__vibezCapture === state) state.result = JSON.stringify(payload);
  };
  const onPageHide = () => finish({ status: 'cancelled' });
  state.cancel = () => finish({ status: 'cancelled' });
  const timer = setTimeout(() => finish({ status: 'error', message: 'Screenshot timed out' }), config.timeoutMs);
  window.addEventListener('pagehide', onPageHide, { once: true });
  const frame = () => new Promise(resolve => requestAnimationFrame(resolve));
  const limit = (w, h) => {
    if (!Number.isFinite(w) || !Number.isFinite(h) || w < 1 || h < 1 || w > 32760 || h > 32760 || w * h > 36000000)
      throw new Error('Page is too large for one screenshot. Use visible page or selection.');
  };
  function chooseRect() {
    return new Promise(resolve => {
      const overlay = document.createElement('div');
      overlay.id = 'vibez-screenshot-selection-overlay';
      Object.assign(overlay.style, {position:'fixed',inset:'0',zIndex:'2147483647',cursor:'crosshair',background:'rgba(0,0,0,.12)',touchAction:'none',userSelect:'none'});
      const box = document.createElement('div');
      Object.assign(box.style, {position:'absolute',display:'none',border:'2px solid #ff6b35',background:'rgba(255,107,53,.12)',pointerEvents:'none',boxSizing:'border-box'});
      const hint = document.createElement('div');
      hint.textContent = config.dragHint;
      Object.assign(hint.style, {position:'absolute',top:'12px',left:'12px',padding:'10px',background:'#17191f',color:'#fff',font:'13px system-ui',pointerEvents:'none'});
      overlay.tabIndex=0; overlay.append(box,hint); document.documentElement.appendChild(overlay);
      const previousFocus=document.activeElement; overlay.focus({preventScroll:true});
      let start = null, done = false;
      const end = rect => { if (done) return; done=true; overlay.remove(); window.removeEventListener('keydown',onKey,true);
        if (previousFocus?.isConnected) previousFocus.focus({preventScroll:true}); resolve(rect); };
      const onKey = event => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); end(null); } };
      cleanupSelection = () => end(null);
      window.addEventListener('keydown',onKey,true);
      const point = e => ({ x:Math.max(0,Math.min(innerWidth,e.clientX)),y:Math.max(0,Math.min(innerHeight,e.clientY)) });
      const rect = e => { const p=point(e); return {x:Math.min(start.x,p.x),y:Math.min(start.y,p.y),width:Math.abs(p.x-start.x),height:Math.abs(p.y-start.y)}; };
      overlay.addEventListener('pointerdown', e => {
        if (e.button !== 0) return; e.preventDefault(); start=point(e);
        try { overlay.setPointerCapture(e.pointerId); } catch (_) { /* synthetic test or lost pointer */ }
      });
      overlay.addEventListener('pointermove', e => {
        if (!start) return; const r=rect(e);
        Object.assign(box.style,{display:'block',left:r.x+'px',top:r.y+'px',width:r.width+'px',height:r.height+'px'});
      });
      overlay.addEventListener('pointerup', e => {
        if (!start) return; const r=rect(e); end(r.width>=4&&r.height>=4 ? {...r,x:r.x+scrollX,y:r.y+scrollY} : null);
      });
      overlay.addEventListener('pointercancel', () => end(null));
      overlay.addEventListener('contextmenu', e => { e.preventDefault(); end(null); });
    });
  }
  function expandLoadedPage() {
    const initialX=scrollX, initialY=scrollY, changes=new Map();
    const set = (el,key,value) => {
      if (!changes.has(el)) {
        const original=document.createElement('div'); original.style.cssText=el.style.cssText;
        changes.set(el,{values:new Map(),top:el.scrollTop,left:el.scrollLeft,originalStyle:el.getAttribute('style'),original:original.style,appliedStyle:el.style.cssText});
      }
      const old=changes.get(el).values;
      if (!old.has(key)) old.set(key,{value:changes.get(el).original.getPropertyValue(key),priority:changes.get(el).original.getPropertyPriority(key),written:value});
      old.get(key).written=value;
      el.style.setProperty(key,value,'important');
      changes.get(el).appliedStyle=el.style.cssText;
    };
    restorePage = () => {
      for (const [el,old] of [...changes].reverse()) {
        if (el.style.cssText===old.appliedStyle) {
          if (old.originalStyle===null) el.removeAttribute('style'); else el.setAttribute('style',old.originalStyle);
          continue;
        }
        for (const [key,v] of old.values) {
          if (el.style.getPropertyValue(key)!==v.written) continue;
          if (v.value) el.style.setProperty(key,v.value,v.priority); else el.style.removeProperty(key);
        }
      }
      for (const [el,old] of changes) { el.scrollTop=old.top; el.scrollLeft=old.left; }
      scrollTo(initialX,initialY); changes.clear();
    };
    // Measure before modifying. Restrict expansion to substantial loaded scrollers.
    const scrollers=[...document.querySelectorAll('main,[role="main"],section,article,div')].slice(0,5000).filter(el=> {
      const r=el.getBoundingClientRect(),s=getComputedStyle(el);
      return r.width>=innerWidth*.2 && r.height>=innerHeight*.18 && r.bottom>0 && r.top<innerHeight &&
        /(auto|scroll)/.test(s.overflowY) && el.scrollHeight>el.clientHeight+40;
    }).map(el=>({el,height:el.scrollHeight,width:el.getBoundingClientRect().width}));
    for (const {el,height,width} of scrollers) {
      limit(width,height);
      for (let p=el;p;p=p.parentElement) {
        const style=getComputedStyle(p), box=p.getBoundingClientRect();
        if (style.position==='fixed') {
          set(p,'position','absolute'); set(p,'inset','auto');
          set(p,'left',(box.left+initialX)+'px'); set(p,'top',(box.top+initialY)+'px');
          set(p,'box-sizing','border-box'); set(p,'width',box.width+'px');
        }
        set(p,'max-height','none'); set(p,'height','auto'); set(p,'overflow-y','visible'); set(p,'overflow-x','visible');
        set(p,'min-height',height+'px'); set(p,'flex-shrink','0');
      }
      set(el,'height',height+'px'); el.scrollTop=0;
    }
    for (const root of [document.documentElement,document.body]) {
      set(root,'overflow-y','visible'); set(root,'max-height','none'); set(root,'height','auto');
      set(root,'scroll-behavior','auto');
    }
    scrollTo(0,0);
    // Explicit document clipping is essential: engines may otherwise size HTML
    // captures to the viewport even after nested scroll containers are expanded.
    let width=Math.max(innerWidth,document.documentElement.scrollWidth);
    let height=Math.max(innerHeight,document.documentElement.scrollHeight,document.body.scrollHeight);
    for(const {el} of scrollers) { const r=el.getBoundingClientRect();height=Math.max(height,r.bottom+scrollY);width=Math.max(width,r.right+scrollX); }
    width=Math.ceil(width);height=Math.ceil(height);limit(width,height);
    set(document.documentElement,'min-height',height+'px');set(document.body,'min-height',height+'px');
    fullGeometry={x:0,y:0,width,height};
  }
  (async () => {
    try {
      const options={dpr:1,invalidate:true,cache:'disabled',useProxy:'',backgroundColor:'#ffffff'};
      if (config.mode==='selection') {
        const r=await chooseRect(); if (settled) return;
        if (!r) { finish({status:'cancelled'}); return; } options.clip=r;
      } else if (config.mode==='visible') options.clip='viewport';
      else if (config.mode==='full') { expandLoadedPage(); options.clip=fullGeometry; }
      else throw new Error('Unsupported screenshot mode');
      await frame(); await frame(); if (settled) return;
      if (config.mode==='full') {
        const root=document.documentElement;
        limit(Math.max(root.scrollWidth,innerWidth),Math.max(root.scrollHeight,document.body.scrollHeight,innerHeight));
      }
      const capture=await window.snapdom(document.documentElement,options);
      if (settled) return;
      limit(capture.meta.w0,capture.meta.h0);
      const canvas=await capture.toCanvas({dpr:1,scale:1});
      if (settled) return;
      limit(canvas.width,canvas.height);
      const blob=await new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(new Error('Empty screenshot')),'image/png'));
      if (settled) return;
      if (blob.size>24*1024*1024) throw new Error('Screenshot is too large to copy safely');
      const dataUrl=await new Promise((resolve,reject)=> {
        const r=new FileReader(); r.onload=()=>resolve(r.result); r.onerror=()=>reject(new Error('Cannot read screenshot')); r.readAsDataURL(blob);
      });
      finish({status:'ok',dataUrl,width:canvas.width,height:canvas.height,geometry:fullGeometry,meta:capture.meta});
    } catch (error) { finish({status:'error',message:String(error?.message||error).slice(0,300)}); }
  })();
  return 'started';
})();
