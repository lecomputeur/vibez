'use strict';
(function(root){
  // Keep only the current context and its verified connection, never credentials.
  function createConnectionStatus(){
    let web=null,auto=null,engineStopped=false;
    const busy=new Set(['starting','authorizing','connecting','registering']);
    function receive(event){
      if(event?.type==='error'&&event.code==='engine_stopped'){engineStopped=true;auto=null;}
      if(engineStopped)return view();
      if(event?.type==='web_connector'){
        const next={
          id:event.project?.id||null,name:event.project?.name||'',folder:event.folder||null,
          binding:event.workspace_binding||event.folder||null,
          kind:event.project?.kind||null,draft:event.project?.draft===true,
          enabled:event.enabled===true,tunnel:event.tunnel_status,
          manual:event.manually_paused===true
        };
        if(!web||web.id!==next.id||web.binding!==next.binding||
          (auto?.status==='connected'&&(!next.enabled||next.tunnel!=='running'||next.manual)))auto=null;
        web=next;
      }else if(event?.type==='web_auto'&&web?.id&&event.project_id===web.id){
        const verified=web.folder&&web.enabled&&web.tunnel==='running'&&!web.manual;
        auto={status:event.status==='connected'&&!verified?'paused':event.status,pauseReason:event.pause_reason};
      }
      return view();
    }
    function view(){
      const result=(state,key)=>({state,key,kind:web?.kind||null,draft:web?.draft===true,projectName:web?.id?web.name:'',
        folderName:web?.id&&web.folder?(web.folder.split(/[\\/]/).filter(Boolean).pop()||web.folder):''});
      if(engineStopped)return result('error','connectionError');
      if(!web?.id)return result('no_project','connectionNoProject');
      if(!web.folder)return result('no_folder','connectionNoFolder');
      if(busy.has(auto?.status))return result('connecting','connectionConnecting');
      if(auto?.status==='error'||web.tunnel==='failed')return result('error','connectionError');
      if(web.manual||auto?.pauseReason==='manual')return result('manual','connectionManual');
      if(auto?.pauseReason==='sign_in')return result('sign_in','connectionSignIn');
      if(auto?.status==='connected'&&web.enabled&&web.tunnel==='running')return result('connected','connectionConnected');
      if(web.tunnel==='starting')return result('connecting','connectionConnecting');
      if(['paused','cancelled','connected'].includes(auto?.status))return result('paused','connectionPaused');
      return result('disconnected','connectionDisconnected');
    }
    return {receive,view};
  }
  const api={createConnectionStatus};
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.vibezConnectionStatus=api;
})(typeof window==='object'?window:globalThis);
