// Mistral builds a generated file (an image, for one) as a blob, clicks a
// download anchor, and removes the anchor and revokes the blob URL in the same
// task. The native download is reissued a moment later (chat_downloads.rs), so
// keep exactly those clicked blob URLs alive briefly and remember their names.
// Nothing here chooses a local path or leaves the page's own session.
(()=>{
  if(!/^(chat|vibe)\.mistral\.ai$/.test(location.hostname)||window.__vibezBlobNames)return;
  const names=new Map(),revoke=URL.revokeObjectURL.bind(URL),KEEP_MS=30000,MAX=16;
  const remember=anchor=>{
    const url=anchor&&anchor.href;
    if(typeof url!=='string'||!url.startsWith('blob:')||!anchor.hasAttribute('download'))return;
    names.set(url,String(anchor.download||'').slice(0,200));
    if(names.size>MAX)names.delete(names.keys().next().value);
  };
  document.addEventListener('click',event=>{
    const target=event.target;
    if(target instanceof Element)remember(target.closest('a[download]'));
  },true);
  const click=HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click=function(){remember(this);return click.apply(this,arguments);};
  URL.revokeObjectURL=function(url){
    const key=String(url);
    if(!names.has(key))return revoke(url);
    setTimeout(()=>{names.delete(key);revoke(key);},KEEP_MS);
  };
  window.__vibezBlobNames=names;
})();
