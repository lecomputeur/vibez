'use strict';
// Tab model of the right-hand panel: Files and Advanced (environment, project
// rules, tone and context, changes), both always present, in a remembered
// order. The viewer's last open tab is restored, except that a fresh start
// and a new folder link always open Files. A stored order or last-open tab
// from before the Project tab merged into Advanced is ignored: unknown names
// fall back to Files.
(()=>{
const TABS=['files','advanced'];
function normalizeOrder(order){
 const out=[];
 for(const tab of Array.isArray(order)?order:[])if(TABS.includes(tab)&&!out.includes(tab))out.push(tab);
 for(const tab of TABS)if(!out.includes(tab))out.push(tab);
 return out;
}
function normalizePrefs(value){
 const source=value&&typeof value==='object'?value:{};
 return {tab_order:normalizeOrder(source.tab_order)};
}
// `savedTab` is the tab the viewer last opened; `persist` stores the order
// per installation; `remember` stores the open tab for this viewer.
function createPanelTabs({prefs=null,savedTab=null,persist=()=>{},remember=()=>{}}={}){
 let state=normalizePrefs(prefs);
 let current=TABS.includes(savedTab)?savedTab:'files';
 const listeners=[];
 const notify=()=>{for(const fn of listeners)fn(snapshot());};
 function snapshot(){return {order:[...state.tab_order],current,tab_order:[...state.tab_order]};}
 function select(name,automatic=false){
  if(!TABS.includes(name))name=state.tab_order[0];
  current=name;if(!automatic)remember(name);notify();return current;
 }
 function apply(next){state=normalizePrefs(next);notify();return snapshot();}
 function reorder(nextOrder){
  const tab_order=normalizeOrder(nextOrder);
  if(tab_order.join()===state.tab_order.join())return snapshot();
  apply({tab_order});persist({tab_order});return snapshot();
 }
 // Drop `tab` on `target`: it takes the target's place, before or after it.
 function move(tab,target,after=false){
  if(tab===target||!TABS.includes(tab)||!TABS.includes(target))return snapshot();
  const rest=state.tab_order.filter(name=>name!==tab),at=rest.indexOf(target);
  rest.splice(at+(after?1:0),0,tab);return reorder(rest);
 }
 function resetOrder(){return reorder(TABS);}
 // A new folder link always shows the files, whatever the order.
 function folderLinked(){return select('files',true);}
 return {state:snapshot,select,apply,reorder,move,resetOrder,folderLinked,onChange(fn){listeners.push(fn);},TABS:[...TABS]};
}
const api={createPanelTabs,normalizeOrder,normalizePrefs,TABS:[...TABS]};
if(typeof module==='object'&&module.exports)module.exports=api;
if(typeof window!=='undefined')window.vibezPanelTabs=api;
})();
