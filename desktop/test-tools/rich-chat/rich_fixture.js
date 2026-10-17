(() => {
  // Entirely synthetic content. No timers or artificial per-scroll computation.
  // Rich Markdown structure, nested flex layout, scroll pane and sticky code
  // headers model common chat UI features; they are not captured Mistral DOM.
  document.querySelectorAll('style').forEach(e => e.remove());
  const style = document.createElement('style');
  style.textContent = `
    *{box-sizing:border-box}html,body{margin:0;height:100%;overflow:hidden}
    body{font:15px/1.65 sans-serif;background:#18191c;color:#e8e8eb}
    .app{position:fixed;inset:0;height:100%;display:flex}.sidebar{width:220px;flex-shrink:0;padding:24px;background:#121316;border-right:1px solid #303138}
    .side-row{padding:12px;border-radius:7px;margin:4px 0;color:#a7a9b3}
    main{flex:1;min-width:0;min-height:0;height:100%;display:flex;flex-direction:column;position:relative}
    header{height:54px;flex-shrink:0;display:flex;align-items:center;justify-content:space-between;padding:0 24px;border-bottom:1px solid #313238;background:#18191ce8}
    #chat{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;scroll-behavior:auto;position:relative;padding:20px 28px 60px}
    .messages{max-width:780px;margin:auto;display:flex;flex-direction:column;gap:36px}
    article{position:relative;min-width:0}.user{align-self:flex-end;max-width:85%;padding:12px 18px;border-radius:20px;background:#303239}
    .role{display:flex;align-items:center;gap:9px;font-weight:bold;color:#f1f1f4}.avatar{width:28px;height:28px;background:#fa7d35;border-radius:8px;display:grid;place-items:center}
    .markdown p{margin:18px 0}.markdown h3{font-size:19px;margin:24px 0 12px}.markdown li{margin:7px 0}
    .codebox{border:1px solid #363840;border-radius:10px;background:#111216;margin:20px 0;position:relative}
    .code-head{position:sticky;top:0;display:flex;align-items:center;justify-content:space-between;background:#24262ce8;backdrop-filter:blur(8px);padding:7px 13px;border-bottom:1px solid #373943;border-radius:9px 9px 0 0;z-index:1;font-size:12px}
    pre{padding:16px;margin:0;overflow:auto;font:13px/1.65 monospace}code .k{color:#ba91e8}code .f{color:#89b8eb}code .s{color:#9bd3a6}code .n{color:#edb775}code .c{color:#7e8493}
    .table-wrap{overflow:auto;border:1px solid #3b3d46;border-radius:7px;margin:18px 0}table{border-collapse:collapse;width:100%}th,td{padding:8px 12px;border:1px solid #3b3d46;white-space:nowrap;font-size:13px}th{background:#25272d}
    blockquote{border-left:3px solid #777d91;margin:16px 0;padding:2px 18px;background:#23252b}
    .actions{display:flex;gap:14px;color:#a5a8b5;margin-top:14px}button{border:0;background:transparent;color:inherit;padding:4px;cursor:pointer}svg{width:17px;height:17px}
    .composer{flex-shrink:0;max-width:850px;width:90%;margin:12px auto 20px;padding:14px 18px;border:1px solid #454752;border-radius:22px;background:#27292f;box-shadow:0 6px 25px #0003}.input{min-height:27px;outline:none}.hint{font-size:11px;color:#8d929f;margin-top:7px}
  `;
  // Use the loaded local stylesheet's CSSOM. The local offline test page has
  // a strict CSP which rejects newly inserted inline style elements.
  const sheet = document.styleSheets[0];
  if(!sheet) throw new Error('Missing local stylesheet');
  while(sheet.cssRules.length) sheet.deleteRule(0);
  for(const rule of style.textContent.matchAll(/[^{}]+\{[^{}]*\}/g)) sheet.insertRule(rule[0],sheet.cssRules.length);
  const icon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M6 8h12v12H6z M9 8V4h12v12h-3"/></svg>';
  const topics = ['Planning van de offline test', 'Een robuuste parser', 'Vergelijking van de uitkomsten', 'Documentatie en onderhoud', 'Analyse van een lange dataset'];
  const sentences = [
    'We gebruiken uitsluitend verzonnen gegevens om de vorm van een lang gesprek na te bootsen. De resultaten zijn daardoor herhaalbaar zonder een account te openen.',
    'Deze aanpak verdeelt het probleem in kleine stappen. Elke stap heeft een duidelijke invoer, een controleerbare uitvoer en een voorbeeld dat los van de rest kan worden uitgevoerd.',
    'Een tabel helpt bij het vergelijken van de verschillende opties. De code hieronder toont de verwerking van een reeks records, inclusief een controle voor ontbrekende waarden.',
    'Bij een fout bewaren we de oorspronkelijke gegevens. Daarna wordt de oorzaak beschreven, zodat een volgende poging dezelfde aannames kan gebruiken.'
  ];
  function answer(i) {
    const lines = Array.from({length:48},(_,j)=>'<span class="k">const</span> <span class="f">record_'+j+'</span> = { <span class="s">label</span>: <span class="s">"sample-'+i+'-'+j+'"</span>, <span class="s">value</span>: <span class="n">'+(i+j)+'</span> }; <span class="c">// synthetic row</span>').join('\n');
    const rows = Array.from({length:12},(_,j)=>'<tr><td>Optie '+j+'</td><td>'+((i+j)%31)+'</td><td>Herhaalbaar</td><td>Lokale gegevens</td><td>Controle '+j+'</td></tr>').join('');
    return '<article class="assistant"><div class="role"><span class="avatar">M</span>Testassistent</div><div class="markdown"><h3>'+topics[i%topics.length]+'</h3>'+sentences.map(s=>'<p>'+s+' <strong>Voorbeeld '+i+'</strong> met <em>controleerbare stappen</em> en <code>lokale_invoer</code>.</p>').join('')+'<ol><li>Verzamel de synthetische records en controleer hun vorm.</li><li>Voer de bewerking uit met een vaste volgorde.<ul><li>Bewaar het resultaat.</li><li>Vergelijk de tabel met de verwachte waarden.</li></ul></li><li>Beschrijf de beperkingen van het voorbeeld.</li></ol><div class="codebox"><div class="code-head"><span>javascript · voorbeeld '+i+'</span><button aria-label="Kopieer voorbeeld">'+icon+' Kopiëren</button></div><pre><code>'+lines+'</code></pre></div><div class="table-wrap"><table><thead><tr><th>Naam</th><th>Waarde</th><th>Status</th><th>Bron</th><th>Controle</th></tr></thead><tbody>'+rows+'</tbody></table></div><blockquote><p>Dit is volledig synthetische inhoud. De lengte modelleert een uitgebreid technisch gesprek.</p></blockquote><p>'+sentences[1]+'</p></div><div class="actions">'+Array.from({length:4},()=>'<button>'+icon+'</button>').join('')+'</div></article>';
  }
  const originalAnswer=answer;
  answer = function(i) {
    const first=originalAnswer(i);
    const rich=first.slice(first.indexOf('<div class="markdown">')+22,first.indexOf('<div class="actions">')-6);
    const sections=Array.from({length:16},(_,j)=>'<section class="rich-section markdown"><h2>Uitgebreide analyse '+(j+1)+' 📊 🧪 ✅</h2>'+rich+'</section>').join('');
    return '<article class="assistant"><div class="role"><span class="avatar">M</span>Offline testassistent</div><div class="answer-body">'+sections+'</div><div class="actions">Einde antwoord '+i+'</div></article>';
  };
  const count = 80;
  document.body.innerHTML = '<div class="app"><aside class="sidebar"><h3>Synthetische chats</h3>'+topics.map(t=>'<div class="side-row">'+t+'</div>').join('')+'</aside><main><header><b>Lange lokale testchat</b><span>Offline · synthetisch</span></header><div id="chat"><div class="messages">'+Array.from({length:count},(_,i)=>i%2===0?'<article class="user">Kun je voorbeeld '+i+' uitwerken voor '+topics[i%topics.length].toLowerCase()+'? Geef code, een tabel en een uitleg van de stappen.</article>':answer(i)).join('')+'</div></div><div class="composer"><div class="input" contenteditable="true" aria-label="Synthetische berichtinvoer">Hier kun je een lokaal testbericht schrijven.</div><div class="hint">Geen verbinding, account of privégesprekken</div></div></main></div>';
  const chat = document.getElementById('chat');
  window.__scrollStats = {wheelEvents:0,trustedWheelEvents:0,scrollEvents:0,minY:0,maxY:0};
  chat.addEventListener('wheel', e=>{__scrollStats.wheelEvents++;if(e.isTrusted)__scrollStats.trustedWheelEvents++;},{passive:true});
  chat.addEventListener('scroll', ()=>{__scrollStats.scrollEvents++;__scrollStats.minY=Math.min(__scrollStats.minY,chat.scrollTop);__scrollStats.maxY=Math.max(__scrollStats.maxY,chat.scrollTop);},{passive:true});
  if(getComputedStyle(document.querySelector('.app')).display!=='flex'||chat.clientHeight>=innerHeight||chat.clientHeight<100) throw new Error('Fixture CSS or scroll pane is invalid');
  sheet.insertRule('.rich-section,article.assistant{display:flow-root}',sheet.cssRules.length);

  chat.scrollTop = Math.floor((chat.scrollHeight-chat.clientHeight)/2);
  __scrollStats.minY = __scrollStats.maxY = chat.scrollTop;
  window.__benchResult = () => ({...__scrollStats,scrollY:chat.scrollTop,innerWidth,innerHeight,appHeight:document.querySelector('.app').clientHeight,mainHeight:document.querySelector('main').clientHeight,height:chat.scrollHeight,viewportHeight:chat.clientHeight,display:getComputedStyle(document.querySelector('.app')).display,messages:document.querySelectorAll('article').length,assistantAnswers:document.querySelectorAll('article.assistant').length,sections:document.querySelectorAll('section.rich-section').length,measuredContainment:window.__measuredContainment||null,contentVisibilitySupported:CSS.supports('content-visibility','auto'),nodes:document.querySelectorAll('*').length,textCharacters:document.body.textContent.length});
  window.__startAnimation = () => {
    const initial = chat.scrollTop;
    window.__animation = {frames:0,done:false};
    function step() {
      __animation.frames++;
      chat.scrollTop = initial + 1000*Math.sin(__animation.frames*Math.PI/120);
      if(__animation.frames<600) requestAnimationFrame(step);
      else __animation.done=true;
    }
    requestAnimationFrame(step);
  };
  document.documentElement.dataset.vibezOfflineFixture='rich40';
  [...document.querySelectorAll('article.assistant')].forEach((el,i)=>{el.dataset.vibezMessage='assistant';el.dataset.vibezReply=String(i);const mark=document.createElement('p');mark.textContent='VIBEZ_UNIQUE_REPLY_'+String(i).padStart(2,'0')+'_END';el.appendChild(mark);});
  return document.querySelectorAll('article').length;
})()
