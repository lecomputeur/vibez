import re,subprocess

def safe_screen():
 output=subprocess.check_output(['xrandr','--listmonitors'],text=True)
 match=next((re.search(r'(\d+)/\d+x(\d+)/\d+([+-]\d+)([+-]\d+)',line) for line in output.splitlines() if 'DisplayPort-1' in line),None)
 if not match:raise RuntimeError('Scherm 1 ontbreekt; geen proefvenster openen')
 width,height,x,y=map(int,match.groups());safe=(x,y,width,height)
 clients=subprocess.check_output(['xprop','-root','_NET_CLIENT_LIST'],text=True).partition('#')[2].replace(',',' ').split()
 for wid in clients:
  title=subprocess.run(['xprop','-id',wid,'_NET_WM_NAME'],capture_output=True,text=True).stdout.lower()
  if not('wot client' in title or 'world of tanks' in title):continue
  info=subprocess.check_output(['xwininfo','-id',wid],text=True)
  def get(key):return int(next(line.split(':')[1].strip() for line in info.splitlines() if line.strip().startswith(key)))
  gx,gy,gw,gh=(get(k) for k in ['Absolute upper-left X','Absolute upper-left Y','Width','Height'])
  if x<gx+gw and gx<x+width and y<gy+gh and gy<y+height:raise RuntimeError('WoT gebruikt het proefscherm; geen venster openen')
 return safe
