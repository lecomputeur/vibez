// Only the official Work instructions form, verified in form-structure.json
// (test.50). No message text, unrelated form values or private API is read.
((project, action, nonce, expected, value) => {
  const owner = '__vibezProjectRulesForm';
  const reply = data => JSON.stringify(data);
  const visible = node => !!node && node.getClientRects().length > 0;
  const disabled = node => node.disabled || node.getAttribute('aria-disabled') === 'true';
  const route = location.pathname.match(/^\/work\/projects\/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\/?$/i);
  if (location.protocol !== 'https:' || !['chat.mistral.ai','vibe.mistral.ai'].includes(location.hostname) ||
      location.port || !route || route[1].toLowerCase() !== project || !/^[0-9a-f]{32}$/.test(nonce))
    return reply({ready:false,reason:'context_changed'});
  const previous = window[owner];
  if (action === 'status' && previous?.nonce === nonce && previous.project === project && (previous.submitted || previous.closing) && !previous.dialog.isConnected) {
    delete window[owner];
    return reply({closed:true});
  }
  const dialogs = [...document.querySelectorAll('[role="dialog"]')].filter(visible);
  if (dialogs.length !== 1) return reply({ready:false,reason:'form_unavailable'});
  const dialog = dialogs[0], forms = [...dialog.querySelectorAll('form')];
  if (forms.length !== 1 || forms[0].id !== 'instructions-form') return reply({ready:false,reason:'form_unavailable'});
  const form = forms[0], headingId = dialog.getAttribute('aria-labelledby');
  const headings = [...dialog.querySelectorAll('h2')];
  const fields = [...form.querySelectorAll('textarea')], presets = [...form.querySelectorAll('select[name="preset"]')];
  const checks = [...form.querySelectorAll('input[type="checkbox"][role="checkbox"]')];
  const submits = [...form.children].filter(node => node.tagName === 'BUTTON' && node.getAttribute('type') === 'submit');
  const closes = [...dialog.children].filter(node => node.tagName === 'BUTTON' && node.getAttribute('type') === 'button' &&
    ['absolute','top-4','right-4'].every(name => node.classList.contains(name)) && node.children.length === 2 &&
    node.children[0].tagName.toLowerCase() === 'svg' && node.children[1].tagName === 'SPAN' && node.children[1].classList.contains('sr-only'));
  if (!headingId || headings.length !== 1 || headings[0].id !== headingId || !headings[0].textContent.trim() ||
      fields.length !== 1 || fields[0].getAttribute('name') !== 'custom' || fields[0].form !== form ||
      presets.length !== 1 || presets[0].form !== form || checks.length !== 1 || checks[0].form !== form ||
      submits.length !== 1 || submits[0].form !== form || closes.length !== 1 || disabled(closes[0]) || disabled(fields[0]))
    return reply({ready:false,reason:'form_unavailable'});
  const field = fields[0], submit = submits[0], close = closes[0];
  if (action === 'read') {
    const text = field.value;
    window[owner] = {project,nonce,dialog,form,field,submit,close,closing:true,submitted:false};
    close.click();
    if (typeof text !== 'string' || text.length > 8000) return reply({ready:false,reason:'too_long'});
    return reply({ready:true,value:text});
  }
  if (action === 'fill') {
    if (typeof expected !== 'string' || typeof value !== 'string' || expected.length > 8000 || value.length > 8000)
      return reply({ready:false,reason:'too_long'});
    if (field.value !== expected) {close.click();return reply({ready:false,reason:'stale'});}
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')?.set;
    if (!setter) {close.click();return reply({ready:false,reason:'form_unavailable'});}
    window[owner] = {project,nonce,dialog,form,field,submit,close,value,submitted:false,
      preset:presets[0],presetValue:presets[0].value,checkbox:checks[0],includeGlobal:checks[0].checked};
    setter.call(field,value);
    field.dispatchEvent(new Event('input',{bubbles:true}));
    field.dispatchEvent(new Event('change',{bubbles:true}));
    return reply({filled:true});
  }
  const owned = previous?.project === project && previous.nonce === nonce && previous.dialog === dialog && previous.form === form && previous.field === field && previous.submit === submit;
  if (!owned) return reply({ready:false,reason:'context_changed'});
  if (action === 'abort') {close.click();delete window[owner];return reply({cancelled:true});}
  if (action === 'submit' && (previous.preset !== presets[0] || previous.presetValue !== presets[0].value ||
      previous.checkbox !== checks[0] || previous.includeGlobal !== checks[0].checked))
    return reply({ready:false,reason:'form_changed'});
  if (action === 'submit' && !previous.submitted && field.value === previous.value && disabled(submit))
    return reply({ready:false,reason:'submit_pending'});
  if (action === 'submit' && !previous.submitted && field.value === previous.value && !disabled(submit)) {
    previous.submitted = true;
    submit.click();
    return reply({submitted:true});
  }
  return reply({ready:false,reason:action === 'status' ? 'pending' : 'form_changed'});
})(__VIBEZ_RULES_PROJECT__, __VIBEZ_RULES_ACTION__, __VIBEZ_RULES_NONCE__, __VIBEZ_RULES_EXPECTED__, __VIBEZ_RULES_VALUE__)
