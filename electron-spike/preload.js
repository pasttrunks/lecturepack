'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('lecturePackSpike', {
  chooseMode(mode) {
    ipcRenderer.send('lecturepack-spike:choose-mode', mode);
  },
  openResults() {
    ipcRenderer.send('lecturepack-spike:open-results');
  }
});

contextBridge.exposeInMainWorld('lecturePackElectron', {
  request(command, payload) {
    return ipcRenderer.invoke('lecturepack-migration:command', command, payload || {});
  },
  onMessage(callback) {
    const listener = (_event, message) => callback(message);
    ipcRenderer.on('lecturepack-migration:message', listener);
    return () => ipcRenderer.removeListener('lecturepack-migration:message', listener);
  }
});
