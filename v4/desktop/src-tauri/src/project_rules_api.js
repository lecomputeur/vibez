(function projectRulesApi(input) {
  // Runs in the signed-in Mistral page. Reads, or replaces and then re-reads,
  // the rules ("instructions") of one Work or Code project. The result waits in
  // window.__vibezRulesApi for VibeZ to collect; nothing else is touched.
  const { id, kind = 'work', save, instructions } = input || {};
  if (!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(id || '') || !['work', 'code'].includes(kind) || location.origin !== 'https://chat.mistral.ai' || window.top !== window) return 'refused';
  if (save && (typeof instructions !== 'string' || instructions.length > 8000)) return 'refused';
  // Work projects and Code projects are served by separate tRPC routers.
  const route = kind === 'code'
    ? { read: '/api/code-trpc/projects.byId', write: '/api/code-trpc/projects.update' }
    : { read: '/api/trpc/project.byId', write: '/api/trpc/project.updateOneById' };
  window.__vibezRulesApi = { state: 'pending' };
  const read = async () => {
    const query = encodeURIComponent(JSON.stringify({ 0: { json: { id } } }));
    const response = await fetch(route.read + '?batch=1&input=' + query, { credentials: 'same-origin' });
    if (!response.ok) throw new Error('read');
    const project = (await response.json())?.[0]?.result?.data?.json;
    if (!project || project.id !== id) throw new Error('read');
    return typeof project.instructions === 'string' ? project.instructions : '';
  };
  (async () => {
    try {
      if (save) {
        const response = await fetch(route.write + '?batch=1', {
          method: 'POST', credentials: 'same-origin', headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ 0: { json: { id, instructions } } }),
        });
        if (!response.ok) throw new Error('save');
      }
      window.__vibezRulesApi = { state: 'done', id, instructions: await read() };
    } catch (error) {
      window.__vibezRulesApi = { state: 'error' };
    }
  })();
  return 'started';
})
