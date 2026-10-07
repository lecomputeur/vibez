"""Actual toolbar -> capture -> native WebKit paste -> file received by composer."""
import os,time,subprocess,json,base64,io
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
from PIL import Image
S=int(os.environ.get('GDK_SCALE','1'));OUT=Path(os.environ['SHOT_OUTPUT']);OUT.mkdir(parents=True,exist_ok=True)
def xd(*args):return subprocess.check_output(['xdotool',*map(str,args)],stderr=subprocess.DEVNULL,text=True).strip()
def pump():
    while Gtk.events_pending():Gtk.main_iteration_do(False)
def sleep(sec):
    deadline=time.monotonic()+sec
    while time.monotonic()<deadline:pump();time.sleep(.03)
def window(pattern,timeout=12):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            ids=xd('search','--onlyvisible','--name',pattern).splitlines()
            if ids:return ids[-1]
        except subprocess.CalledProcessError:pass
        sleep(.15)
    raise AssertionError('Missing window: '+pattern)
def geom(w):return {k:int(v) for k,v in (line.split('=') for line in xd('getwindowgeometry','--shell',w).splitlines()) if k in ['X','Y','WIDTH','HEIGHT']}
def shot(name):
    path=OUT/name;subprocess.run(['import','-window','root',str(path)],check=True);return Image.open(path).convert('RGB')
def key(k):xd('key','--clearmodifiers',k);sleep(.12)
def click(w,x,y):xd('mousemove','--window',w,int(x*S),int(y*S));xd('click',1);sleep(.2)
clipboard=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
def clear_clip():clipboard.set_text('screenshot-e2e-sentinel',-1);pump();sleep(.1)
def await_png(name,timeout=15):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        pump();pix=clipboard.wait_for_image()
        if pix is not None:
            path=OUT/name;pix.savev(str(path),'png',[],[]);return Image.open(path).convert('RGB')
        sleep(.15)
    shot('failure.png');raise AssertionError('No clipboard PNG after real UI capture')
def events():
    try:return json.loads((OUT/'paste-events.json').read_text())
    except (FileNotFoundError,json.JSONDecodeError):return []
def await_paste(number,expected,name):
    end=time.monotonic()+10
    while time.monotonic()<end:
        values=events()
        if len(values)>=number and values[number-1].get('dataUrl'):
            p=values[number-1]
            assert (p['trusted'] or p.get('bridge')) and p['type']=='image/png' and p['size']>0,p
            assert p['draft']=='Bestaande concepttekst' and p['submits']==0,'Draft altered or sent'
            image=Image.open(io.BytesIO(base64.b64decode(p['dataUrl'].split(',',1)[1]))).convert('RGB')
            assert image.size==expected.size and image.tobytes()==expected.tobytes(),'Pasted pixels differ from screenshot'
            image.save(OUT/f'pasted-{name}.png')
            sleep(.3);assert len(events())==number,'Duplicate paste event'
            print('PASTE_OK:',name,image.size,('native' if p['trusted'] else 'memory compatibility'),'image/png, exact pixels, preserved draft, no send; scale',S,flush=True)
            return
        sleep(.15)
    shot('failure.png');raise AssertionError('Image never arrived in the browser composer: '+str(len(events())))
def count(im,c):return sum(all(abs(a-b)<10 for a,b in zip(px,c)) for px in im.getdata())
def open_chooser(main):
    xd('windowactivate','--sync',main);sleep(.3)
    g=geom(main);im=shot('before-open.png');pts=[]
    for y in range(g['Y']+5*S,g['Y']+50*S):
        for x in range(g['X']+g['WIDTH']//2,g['X']+g['WIDTH']-10*S):
            r,bg,b=im.getpixel((x,y))
            if r>180 and 65<bg<155 and b<90:pts.append((x,y))
    assert len(pts)>100,'Cannot find screenshot toolbar button'
    x=(min(p[0] for p in pts)+max(p[0] for p in pts))//2;y=(min(p[1] for p in pts)+max(p[1] for p in pts))//2
    xd('mousemove',x,y);xd('click',1);w=window('VibeZ · .*test 4');xd('mousemove','--window',w,25*S,25*S);sleep(1)
    d=geom(w);assert d['WIDTH']/S<=342 and d['HEIGHT']/S<=292,('Chooser oversized',d)
    return w
def start_capture(main,mode,copy_only=False):
    dialog=open_chooser(main);shot('chooser.png')
    if copy_only:
        key('Tab');key('Tab');key('Tab');key('space')
    clear_clip();click(dialog,150,{'visible':69,'full':120,'selection':171}[mode])
    if mode=='selection':
        window('^VibeZ screen selection$');sleep(.4);xd('mousemove','--window',main,224*S,178*S);xd('mousedown',1)
        xd('mousemove','--sync','--window',main,104*S,78*S);xd('mouseup',1)
try:
    main=window('VibeZ 3 v3.0.2');sleep(4);n=0
    for mode in ['visible','full','selection']:
        start_capture(main,mode);im=await_png(mode+'.png');n+=1;await_paste(n,im,mode)
        assert count(im,(230,30,40))>5000,(mode,'red missing',im.size)
        blue=count(im,(30,60,230))
        if mode=='full':assert im.height>=1800 and blue>5000,('full page lost bottom',im.size)
        else:assert blue<100,('offscreen content leaked',mode)
        if mode=='selection':assert im.size==(120,100),im.size
        if mode=='visible':
            g=geom(main);assert abs(im.width-g['WIDTH']/S)<=2 and abs(im.height-(g['HEIGHT']/S-54))<=2,im.size
            assert count(im,(160,40,190))>5000,'Canvas missing'
        print('E2E_MODE_OK:',mode,im.size,'scale',S,flush=True)
    # Manual Ctrl+V still works after the option window has closed.
    g=geom(main);click(main,320,g['HEIGHT']/S-50);key('ctrl+v');n+=1;await_paste(n,im,'manual-ctrl-v')
    # Deliberately unavailable composer must not lose the PNG or fake success.
    click(main,770,g['HEIGHT']/S-45);start_capture(main,'visible');im=await_png('no-composer.png')
    window('VibeZ · .*test 4');sleep(1);assert len(events())==n,'Pasted into read-only composer'
    shot('no-composer-fallback.png');key('Escape');click(main,770,g['HEIGHT']/S-45)
    # Opt-out yields a small preview, retains clipboard and allows Save.
    start_capture(main,'visible',copy_only=True);im=await_png('copy-only.png');dialog=window('VibeZ · .*test 4');sleep(.5)
    assert len(events())==n,'Copy-only unexpectedly pasted';shot('copy-only-preview.png')
    # Copy has focus, Tab -> Save. Replace entire GTK filename including extension.
    key('Tab');key('Return');window('Screenshot opslaan|Save screenshot');sleep(.4)
    key('ctrl+l');key('ctrl+a');xd('type','--clearmodifiers','--delay',1,str(OUT/'saved.png'));key('Return');sleep(.5)
    if not (OUT/'saved.png').exists():key('Return')
    end=time.monotonic()+6
    while not (OUT/'saved.png').exists() and time.monotonic()<end:sleep(.2)
    saved=Image.open(OUT/'saved.png').convert('RGB');assert saved.size==im.size and saved.tobytes()==im.tobytes()
    key('Escape');sleep(.3)
    # Capture from a different native app, then automatically paste back into VibeZ.
    external=Gtk.Window();external.set_title('Outside VibeZ fixture');external.set_decorated(False)
    external.set_default_size(140,100);external.move(20,30);area=Gtk.DrawingArea()
    def draw_external(widget,cr):cr.set_source_rgb(10/255,150/255,240/255);cr.paint();return True
    area.connect('draw',draw_external);external.add(area);external.show_all();sleep(.4)
    eg=geom(window('^Outside VibeZ fixture$'));dialog=open_chooser(main);clear_clip();click(dialog,150,171)
    window('^VibeZ screen selection$');sleep(.4)
    xd('mousemove',eg['X']+130*S,eg['Y']+90*S);xd('mousedown',1)
    xd('mousemove','--sync',eg['X']+10*S,eg['Y']+10*S);xd('mouseup',1)
    im=await_png('other-application.png');n+=1;await_paste(n,im,'other-application')
    assert im.size==(120,80) and count(im,(10,150,240))>8000,'Wrong desktop pixels';external.hide()
    dialog=open_chooser(main);clear_clip();click(dialog,150,171);window('^VibeZ screen selection$');key('Escape')
    window('VibeZ · .*test 4');sleep(.4);assert clipboard.wait_for_image() is None and len(events())==n,'Cancel pasted'
    key('Return');im=await_png('after-cancel.png');n+=1;await_paste(n,im,'after-cancel')
    # After another application replaces the clipboard, do not paste the old PNG.
    clear_clip();g=geom(main);click(main,320,g['HEIGHT']/S-50);key('ctrl+v');sleep(.5)
    assert len(events())==n,'Stale screenshot pasted after clipboard replacement'
    key('ctrl+a');key('ctrl+c');sleep(.3)
    assert 'screenshot-e2e-sentinel' in (clipboard.wait_for_text() or ''),'Ordinary text paste regressed'
    print('CLIPBOARD_REPLACEMENT_OK: external text clipboard is preserved, no stale image attachment',flush=True)
    print('SCREENSHOT_E2E_OK: compact chooser; real image paste for 3 modes, Ctrl+V, desktop; copy-only/save; unavailable composer; cancel/retry; scale',S,flush=True)
except Exception:
    shot('failure.png')
    try:
        from urllib.parse import urlparse,unquote
        print('CLIPBOARD_TARGETS:',clipboard.wait_for_targets(),flush=True)
        uris=clipboard.wait_for_uris() or []
        print('CLIPBOARD_FILES:',[(u,Path(unquote(urlparse(u).path)).exists()) for u in uris],flush=True)
        print('FAILED_PASTE_METADATA:',events(),flush=True)
        # Diagnostic only: never turns a failed automatic-paste test green.
        key('Escape');xd('windowactivate','--sync',main);g=geom(main)
        click(main,320,g['HEIGHT']/S-50);key('ctrl+v');sleep(2)
        print('MANUAL_PASTE_METADATA:',[{k:v for k,v in e.items() if k!='dataUrl'} for e in events()],flush=True)
        import subprocess
        subprocess.run(['/usr/bin/python3','tests/clipboard-diagnostic.py'],check=False,timeout=25)
    except Exception as diagnostic_error:print('DIAGNOSTIC_ERROR:',str(diagnostic_error),flush=True)
    raise
