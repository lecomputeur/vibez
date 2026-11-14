(function workChatCover(input) {
  // While VibeZ selects the folder connector in this conversation, Mistral's own
  // menus open and close. Keep them invisible and show one calm message instead.
  // Opacity keeps every element measurable and clickable for VibeZ's own steps.
  const { show, text } = input || {};
  const old = document.getElementById('vibez-work-cover');
  const style = document.getElementById('vibez-work-cover-style');
  if (!show) { old?.remove(); style?.remove(); return 'hidden'; }
  if (!style) {
    const node = document.createElement('style');
    node.id = 'vibez-work-cover-style';
    node.textContent = '[data-radix-popper-content-wrapper],[role=menu],[role=dialog],[role=listbox]{opacity:0!important;transition:none!important}' +
      '#vibez-work-cover{position:fixed;inset:0;z-index:2147483647;display:flex;align-items:center;justify-content:center;' +
      'background:rgba(250,249,247,.72);backdrop-filter:blur(2px);font:500 15px/1.5 system-ui,sans-serif;color:#2b2b2b;cursor:progress}' +
      '#vibez-work-cover div{display:flex;align-items:center;gap:12px;padding:16px 22px;border-radius:12px;background:#fff;box-shadow:0 4px 20px rgba(0,0,0,.12)}' +
      '#vibez-work-cover span{width:16px;height:16px;border-radius:50%;border:2px solid #ff7000;border-right-color:transparent;animation:vibez-spin .8s linear infinite}' +
      '@keyframes vibez-spin{to{transform:rotate(360deg)}}' +
      '@media (prefers-color-scheme:dark){#vibez-work-cover{background:rgba(20,20,20,.72);color:#eee}#vibez-work-cover div{background:#262626}}';
    document.documentElement.append(node);
  }
  if (!old) {
    const cover = document.createElement('div');
    cover.id = 'vibez-work-cover';
    cover.setAttribute('role', 'status');
    cover.setAttribute('aria-live', 'polite');
    const card = document.createElement('div');
    card.append(document.createElement('span'), document.createTextNode(String(text || '').slice(0, 120)));
    cover.append(card);
    document.documentElement.append(cover);
  }
  return 'shown';
})
