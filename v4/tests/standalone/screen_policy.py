import json,os,re,subprocess
from pathlib import Path

CHOICE=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'nl.lecomputeur.vibez4.alpha/safe-output.json'

def personal_choice():
 """The safe screen and windows to avoid, as the app reads them (safe-output.json)."""
 data=json.loads(CHOICE.read_text()) if CHOICE.is_file() else {}
 output=os.environ.get('VIBEZ_SAFE_OUTPUT') or data.get('output')
 if not output:raise RuntimeError('Geen proefscherm ingesteld (VIBEZ_SAFE_OUTPUT of safe-output.json); geen proefvenster openen')
 avoid=[str(name).strip().lower() for name in data.get('avoid_windows',[]) if str(name).strip()]
 return output,avoid

def safe_screen():
 output,avoid=personal_choice()
 listed=subprocess.check_output(['xrandr','--listmonitors'],text=True)
 match=next((re.search(r'(\d+)/\d+x(\d+)/\d+([+-]\d+)([+-]\d+)',line) for line in listed.splitlines() if line.split()[-1:]==[output]),None)
 if not match:raise RuntimeError('Het proefscherm ontbreekt; geen proefvenster openen')
 width,height,x,y=map(int,match.groups());safe=(x,y,width,height)
 if not avoid:return safe
 clients=subprocess.check_output(['xprop','-root','_NET_CLIENT_LIST'],text=True).partition('#')[2].replace(',',' ').split()
 for wid in clients:
  title=subprocess.run(['xprop','-id',wid,'_NET_WM_NAME'],capture_output=True,text=True).stdout.lower()
  if not any(name in title for name in avoid):continue
  info=subprocess.check_output(['xwininfo','-id',wid],text=True)
  def get(key):return int(next(line.split(':')[1].strip() for line in info.splitlines() if line.strip().startswith(key)))
  gx,gy,gw,gh=(get(k) for k in ['Absolute upper-left X','Absolute upper-left Y','Width','Height'])
  if x<gx+gw and gx<x+width and y<gy+gh and gy<y+height:raise RuntimeError('Een te vermijden venster staat op het proefscherm; geen venster openen')
 return safe
