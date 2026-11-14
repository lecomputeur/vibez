(function workConnectorStep(input) {
  const { origin, stage, title, slugPrefix, description, endpoint } = input;
  const allowedOrigin = origin === 'https://chat.mistral.ai' || origin === 'https://vibe.mistral.ai';
  if (!allowedOrigin || location.origin !== origin || window.top !== window) return { state: 'wrong-origin' };
  if (!/^[a-z0-9][a-z0-9_]{2,56}$/.test(slugPrefix || '') || typeof title !== 'string' || title.length < 3 ||
      title.length > 100 || /[\u0000-\u001f\u007f]/.test(title) || typeof description !== 'string' ||
      !description || description.length > 600 || /[\u0000-\u001f\u007f]/.test(description) ||
      !/^https:\/\/[a-z0-9-]+\.trycloudflare\.com\/mcp\/(?:chat-|code-)?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}(?:\/[A-Za-z0-9_-]{43,86})?$/.test(endpoint || '')) {
    return { state: 'invalid-input' };
  }

  const visible = (node) => node.getClientRects().length > 0;
  const hasLabel = (node, names) => names.test((node.getAttribute('aria-label') || '').trim()) ||
    names.test((node.innerText || '').trim());
  const unique = (root, selector, filter = () => true) => {
    const found = [...root.querySelectorAll(selector)].filter((node) => visible(node) && filter(node));
    return found.length === 1 ? found[0] : null;
  };
  const ready = (button) => !button.disabled && button.getAttribute('aria-disabled') !== 'true';
  const connectedList = location.pathname === '/connections' && !location.search && !location.hash;
  const detailMatches = (path) => typeof path === 'string' &&
    new RegExp('^/connections/' + slugPrefix + '(?:_[a-z0-9]{4,12})?$').test(path);
  const headings = 'h1,h2,h3,[role=heading]';
  // VibeZ sets the Mistral site to the app language (en, nl, fr, de, es, it,
  // pt, pl, uk, ar). Exact English/Dutch labels come first; otherwise the
  // controls are recognised by structure plus a word in any of those languages.
  const menuLabel = /^(Nieuwe connector|New connector|Add connector|\+ Add Connector)$/i;
  const connectorWord = /connect|konnekt|konekt|conect|connett|łącznik|конектор|з['’]єднувач|موصل/i;
  const formLabel = /^(Aangepaste connector toevoegen|Add custom connector|Add custom MCP connector)$/i;
  const customWord = /custom|aangepast|personnalis|benutzerdefiniert|eigene|personalizad|personalizzat|niestandardow|własn|користувацьк|власн|مخصص|\bMCP\b/i;
  const noAuth = /^(Geen authenticatie|No authentication|Aucune authentification|Pas d['’]authentification|Keine Authentifizierung|Sin autenticación|Nessuna autenticazione|Sem autenticação|Brak uwierzytelniania|Bez uwierzytelniania|Без автентифікації|بدون مصادقة)$/i;
  const autoDetect = /Automatisch detecteren|Auto-?detect|Détection automatique|Détecter automatiquement|Automatisch erkennen|Automatische Erkennung|Detección automática|Detectar automáticamente|Rilevamento automatico|Rileva automaticamente|Detecção automática|Detectar automaticamente|Wykryj automatycznie|Automatyczne wykrywanie|Автоматичне виявлення|Виявити автоматично|اكتشاف تلقائي|الكشف التلقائي/i;
  const authWord = /authenticat|authentif|autentica|autenticaç|uwierzyteln|автентифік|مصادقة|detect|détect|erkenn|detecc|detecç|rilev|wykry|виявл|كشف|token|токен|OAuth/i;
  const keyLabel = /token|jeton|токен|Bearer/i;
  // Prefer the exact label; else the only control whose label has the word.
  const pick = (nodes, exact, word) => {
    const labelled = nodes.filter((node) => hasLabel(node, exact));
    if (labelled.length) return labelled.length === 1 ? labelled[0] : null;
    const worded = nodes.filter((node) => hasLabel(node, word));
    return worded.length === 1 ? worded[0] : null;
  };
  const ownTitle = () => unique(document, 'h1', (heading) => heading.innerText.trim() === title);

  if (stage === 'detail') {
    if (connectedList) return { state: 'wait' };
    if (!detailMatches(location.pathname) || location.search || location.hash) return { state: 'wrong-page' };
    return ownTitle() ? { state: 'detail', path: location.pathname } : { state: 'wait' };
  }

  if (!connectedList) return { state: 'wrong-page' };
  if (stage === 'open-menu') {
    const button = pick([...document.querySelectorAll('button[aria-haspopup=menu]')]
      .filter((node) => visible(node) && ready(node)), menuLabel, connectorWord);
    if (!button) return { state: 'wait' };
    if (button.getAttribute('aria-expanded') !== 'true') {
      button.dispatchEvent(new PointerEvent('pointerdown', {
        bubbles: true, cancelable: true, pointerId: 1, pointerType: 'mouse', button: 0,
      }));
    }
    return { state: 'advanced' };
  }
  if (stage === 'open-form') {
    const entry = pick([...document.querySelectorAll('[role=menuitem]')]
      .filter((node) => visible(node) && ready(node)), formLabel, customWord);
    if (!entry) return { state: 'wait' };
    entry.click();
    return { state: 'advanced' };
  }

  // The custom connector dialog: its heading, or else its own address field.
  const dialog = unique(document, '[role=dialog]', (node) => Boolean(unique(node, headings, (heading) =>
    formLabel.test(heading.innerText.trim()))) || Boolean(unique(node, 'input#server[name=server]')));
  if (!dialog) return { state: 'wait' };
  const form = unique(dialog, 'form');
  if (!form) return { state: 'wait' };
  const titleField = unique(form, 'input[name=title][type=text]');
  const endpointField = unique(form, 'input#server[name=server]');
  const descriptionField = unique(form, 'input#description[name=description]');
  if (!titleField || !endpointField || !descriptionField) return { state: 'wait' };

  const fill = (field, value) => {
    if (field.disabled || field.readOnly || (field.value && field.value !== value)) return { state: 'unexpected-form' };
    if (!field.value) {
      field.focus();
      field.select();
      document.execCommand('insertText', false, value);
      field.blur();
      // Mistral starts its connection check on these events, as after typing.
      field.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
      field.dispatchEvent(new Event('change', { bubbles: true }));
    }
    return { state: field.value === value ? 'advanced' : 'wait' };
  };

  if (stage === 'title') {
    if (endpointField.value || descriptionField.value) return { state: 'unexpected-form' };
    return fill(titleField, title);
  }
  if (titleField.value !== title) return { state: 'unexpected-form' };
  if (stage === 'endpoint') {
    if (descriptionField.value) return { state: 'unexpected-form' };
    return fill(endpointField, endpoint);
  }
  if (endpointField.value !== endpoint) return { state: 'unexpected-form' };
  if (stage === 'description') return fill(descriptionField, description);
  if (descriptionField.value !== description) return { state: 'unexpected-form' };

  if (stage !== 'auth' && stage !== 'submit') return { state: 'invalid-stage' };
  // The secret project address answers without a key, so Mistral's automatic
  // detection must settle on "no authentication". A key field means it did not.
  const keyField = [...form.querySelectorAll('input[type=password]')].some(visible);
  if (keyField) return { state: 'auth-required' };
  const text = form.innerText || '';
  if (/andere HTTP-status|other than 200|niet naar een geldige|not point to a valid/i.test(text)) {
    return { state: 'wait', reason: 'server-not-detected' };
  }
  if (/OAuth/i.test([...form.querySelectorAll('button,[role=combobox]')].filter(visible)
    .map((node) => node.innerText || '').join(' '))) {
    return { state: 'auth-required' };
  }
  const authLabel = [...form.querySelectorAll('button')].filter(visible).map((node) => (node.innerText || '').trim())
    .find((label) => authWord.test(label)) || '';
  if (keyLabel.test(authLabel)) return { state: 'auth-required' };
  // The form's only submit button, whatever its label in the site language.
  const submit = unique(form, 'button[type=submit]', ready);
  if (!submit || !noAuth.test(authLabel)) {
    // Still undetected: nudge the address field again, at most every 3 s.
    const kick = window.__vibezWorkDetectKick || 0;
    if (Date.now() - kick > 3000 && autoDetect.test(authLabel)) {
      window.__vibezWorkDetectKick = Date.now();
      endpointField.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
      endpointField.dispatchEvent(new Event('change', { bubbles: true }));
      return { state: 'wait', reason: 'detect-kick' };
    }
    return { state: 'wait', reason: authLabel ? 'detecting' : 'checking' };
  }
  if (stage === 'auth') return { state: 'advanced' };
  if (submit.hasAttribute('data-vibez-work-submitted')) return { state: 'submitted' };
  submit.setAttribute('data-vibez-work-submitted', '');
  submit.click();
  return { state: 'submitted' };
})
