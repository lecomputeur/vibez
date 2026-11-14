// Run inside the original Mistral document: blob URLs and cookies never leave
// its browser session. A native Save dialog, not this script, picks the path.
(async()=>{
  const url=__VIBEZ_DOWNLOAD_URL__;
  let name=[...document.querySelectorAll('a[download]')].find(a=>a.href===url)?.download||window.__vibezBlobNames?.get(url);
  if(!name){
    const extensions={
      'application/vnd.oasis.opendocument.text':'odt','application/vnd.oasis.opendocument.spreadsheet':'ods',
      'application/vnd.oasis.opendocument.presentation':'odp','application/vnd.openxmlformats-officedocument.wordprocessingml.document':'docx',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':'xlsx','application/vnd.openxmlformats-officedocument.presentationml.presentation':'pptx',
      'application/msword':'doc','application/vnd.ms-excel':'xls','application/pdf':'pdf',
      'text/plain':'txt','text/markdown':'md','text/html':'html','text/csv':'csv',
      'image/png':'png','image/jpeg':'jpg','image/gif':'gif','image/webp':'webp','application/zip':'zip'
    };
    let extension='';try{const response=await fetch(url);extension=extensions[(response.headers.get('content-type')||'').split(';')[0].trim().toLowerCase()]||'';}catch(_){ }
    name='Mistral-file'+(extension?'.'+extension:'');
  }
  const anchor=document.createElement('a');anchor.href=url;anchor.download=name;
  document.body.append(anchor);anchor.click();anchor.remove();
})()
