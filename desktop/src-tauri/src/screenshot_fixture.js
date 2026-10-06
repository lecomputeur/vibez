/* Offline synthetic UI-test content only; never injected during ordinary use. */
(() => {
  document.body.style.cssText='margin:0;background:white;color:#222;font:16px system-ui';
  document.body.innerHTML='<div id="shot-host" style="position:fixed;inset:0;display:flex;overflow:hidden"><aside style="width:80px;flex-shrink:0;background:rgb(0,200,180)">Sidebar</aside><main id="shot-scroll" style="height:100%;flex:1;overflow-y:auto;padding:0;max-width:none"><div style="height:1800px;position:relative;background:white"><div style="position:absolute;left:24px;top:24px;width:120px;height:100px;background:rgb(230,30,40)"></div><p style="position:absolute;left:24px;top:160px">Native screenshot — offline test</p><canvas id="shot-canvas" width="100" height="80" style="position:absolute;left:24px;top:230px"></canvas><div style="position:absolute;left:24px;top:1400px;width:120px;height:100px;background:rgb(30,60,230)"></div></div></main></div>';
  const canvas=document.getElementById('shot-canvas'),c=canvas.getContext('2d');c.fillStyle='rgb(160,40,190)';c.fillRect(0,0,100,80);
  // Additional restrictive CSP deliberately blocks data/blob image reconstruction.
  // WebKit's native snapshot must still capture the real page and canvas pixels.
  const meta=document.createElement('meta');meta.httpEquiv='Content-Security-Policy';meta.content="default-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self'; script-src 'self'";document.head.append(meta);
})();
