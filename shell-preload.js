const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('vibezShell', {
  getState: () => ipcRenderer.invoke('vibez:shell:get-state'),
  action: (action) => ipcRenderer.send('vibez:shell:action', action),
  onState: (callback) => {
    const listener = (_event, state) => callback(state);
    ipcRenderer.on('vibez:shell:state', listener);
    return () => ipcRenderer.removeListener('vibez:shell:state', listener);
  },
});
