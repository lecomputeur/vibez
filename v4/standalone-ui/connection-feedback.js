'use strict';
(function(root){
 // Only stable error codes choose user actions. Provider text, HTTP status and
 // credentials never decide whether an account must sign in again.
 const restore=['connectionRestore','connect'];
 const feedback={
  sign_in:['auto_sign_in','connectionSignIn','connect'],
  permission:['auto_permission','connectionSettings','settings'],
  workspace_unavailable:['connectionFolderHelp','connectionCheckFolder','folder'],
  readiness_auth:['connectionFilesAuthHelp',...restore],
  connector_auth:['connectionFilesAuthHelp',...restore],
  connector_auth_schema:['connectionFilesAuthHelp',...restore],
  authentication_unconfirmed:['connectionAuthUnconfirmedHelp',...restore],
  connector_sync:['connectionSyncHelp',...restore],
  connector_cleanup:['connectionCleanupHelp',...restore],
  execution:['connectionReachabilityHelp',...restore],
  readiness:['connectionReachabilityHelp',...restore],
  server_unreachable:['connectionReachabilityHelp',...restore],
  network:['auto_network',...restore],
  tunnel:['auto_tunnel',...restore],
  // After three automatic attempts: say which side failed (13 Nov 2026).
  tunnel_cloudflare:['auto_tunnel_cloudflare',...restore],
  tunnel_network:['auto_tunnel_network',...restore],
  tools:['auto_tools',...restore],
  rate_limit:['connectionRateLimitHelp','filesRetry','connect'],
  not_found:['connectionMissingHelp',...restore],
  ownership:['auto_ownership','connectionSettings','settings'],
  invalid_response:['connectionResponseHelp',...restore],
  invalid_request:['connectionResponseHelp',...restore],
  mistral_error:['connectionResponseHelp',...restore],
  engine_stopped:['engineStopped',null,'none']
 };
 function errorObject(error){
  if(error&&typeof error==='object'&&!Array.isArray(error))return error;
  if(typeof error==='string'&&error.length<=32768&&error.trim().startsWith('{')){
   try{const parsed=JSON.parse(error);if(parsed&&typeof parsed==='object'&&!Array.isArray(parsed))return parsed;}catch(_){}
  }
  return {};
 }
 function connectionFeedback({automatic={},actionError=null,linked=false}={}){
  const source=actionError?errorObject(actionError):automatic;
  const code=source.error_code||source.code;
  const known=Object.hasOwn(feedback,code)?feedback[code]:null;
  // Explicit account expiry and a paused connection are separate states. A
  // paused project is resumed only by a user's Connect action, never here.
  if(!actionError&&automatic.status!=='error'){
   if(automatic.status==='connected'&&Number.isSafeInteger(automatic.connector_cleanup_pending)&&automatic.connector_cleanup_pending>0)return {messageKey:'connectionCleanupHelp',buttonKey:'connectionRestore',action:'connect',errorCode:'connector_cleanup'};
   if(automatic.pause_reason==='sign_in')return {messageKey:null,buttonKey:'connectionSignIn',action:'connect',errorCode:'sign_in'};
   return {messageKey:null,buttonKey:null,action:'connect',errorCode:null};
  }
  if(code==='work_setup_failed'){
   // Fixed backend names only: which part of the Work setup failed.
   const verify=source.work_failure==='verify';
   return {messageKey:verify?'connectionWorkVerifyHelp':'connectionWorkSetupHelp',buttonKey:'connectionRestore',action:'connect',errorCode:code};
  }
  if(known)return {messageKey:known[0],buttonKey:known[1],action:known[2],errorCode:code};
  if(actionError)return {messageKey:null,buttonKey:null,action:'connect',errorCode:null};
  return {messageKey:'auto_error',buttonKey:linked?'connectionRestore':'chooseWorkspace',action:linked?'connect':'folder',errorCode:null};
 }
 const api={connectionFeedback};
 if(typeof module==='object'&&module.exports)module.exports=api;
 else root.vibezConnectionFeedback=api;
})(typeof window==='object'?window:globalThis);
