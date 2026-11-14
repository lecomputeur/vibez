(() => {
  // Split cookie pairs, not a double-escaped regexp embedded in a Rust string.
  const clean = value => /^[a-zA-Z-]{1,40}$/.test(value || '') ? value : '<none>';
  let cookie = '<none>';
  try {
    const pair = document.cookie.split(';').map(s => s.trim()).find(s => s.startsWith('NEXT_LOCALE='));
    if (pair) cookie = clean(decodeURIComponent(pair.slice('NEXT_LOCALE='.length)));
  } catch (_) { cookie = '<unavailable>'; }
  return 'document-cookie=' + cookie + '; html=' + clean(document.documentElement?.lang)
    + '; navigator=' + clean(navigator.language) + '; host=' + location.hostname;
})()
