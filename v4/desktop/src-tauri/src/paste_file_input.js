/* Explicit screenshot -> the existing composer upload input. No disk access,
   no endpoint calls, no submit clicks, no enabling disabled controls. */
(() => {
  'use strict';
  const receipt=window.__vibezPasteReceipt,editor=receipt?.editor,input=receipt?.upload;
  if(!receipt||receipt.received||!editor?.isConnected||!input?.isConnected||input.disabled||input.files?.length||editor.getRootNode().activeElement!==editor)
    return JSON.stringify({ok:false});
  const raw=atob(__VIBEZ_SCREENSHOT_PNG__),bytes=new Uint8Array(raw.length);
  for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
  const name='VibeZ-screenshot-'+Date.now()+'.png';
  const file=new File([bytes],name,{type:'image/png'}),data=new DataTransfer();data.items.add(file);
  input.files=data.files;
  if(input.files.length!==1||input.files[0].size!==bytes.length)return JSON.stringify({ok:false});
  receipt.fileNames=[name];receipt.received=true;receipt.images=1;receipt.bridge=true;
  input.dispatchEvent(new Event('input',{bubbles:true,composed:true}));
  input.dispatchEvent(new Event('change',{bubbles:true,composed:true}));
  // 'ok' means delivery only. Rust separately waits for visible attachment UI.
  return JSON.stringify({ok:true});
})();
