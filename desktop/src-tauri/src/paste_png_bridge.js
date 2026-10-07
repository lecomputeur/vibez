/* User-requested, memory-only PNG transfer for WebKitGTK's blocked image clipboard.
   Receives only this captured PNG, never file paths or arbitrary clipboard data. */
(() => {
  'use strict';
  const receipt=window.__vibezPasteReceipt, editor=receipt?.editor;
  if(!receipt?.received || !receipt.trusted || receipt.images!==0 || !editor?.isConnected)
    return JSON.stringify({ok:false,reason:'not-an-empty-native-paste'});
  if(editor.getRootNode().activeElement!==editor || editor.disabled || editor.readOnly)
    return JSON.stringify({ok:false,reason:'composer-changed'});
  const raw=atob(__VIBEZ_SCREENSHOT_PNG__);
  const bytes=new Uint8Array(raw.length);
  for(let i=0;i<raw.length;i++) bytes[i]=raw.charCodeAt(i);
  const image=new File([bytes],'VibeZ-screenshot.png',{type:'image/png'});
  const data=new DataTransfer();data.items.add(image);
  if(data.files.length!==1 || data.files[0].size!==bytes.length)
    return JSON.stringify({ok:false,reason:'memory-file-unavailable'});
  const event=new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true,composed:true});
  Object.defineProperty(event,'vibezScreenshotBridge',{value:true});
  editor.dispatchEvent(event);
  return JSON.stringify({ok:receipt.images===1 && receipt.bridge===true,method:'memory'});
})();
