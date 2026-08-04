'use strict';

const { contextBridge, ipcRenderer } = require('electron');

// The production renderer receives only the narrow request/event surface. No
// Node, Electron, filesystem, or process handles cross the isolation boundary.
contextBridge.exposeInMainWorld('lecturePackElectron', {
  request(command, payload) {
    return ipcRenderer.invoke(
      'lecturepack-production:command',
      command,
      payload || {}
    );
  },
  onMessage(callback) {
    const listener = (_event, message) => callback(message);
    ipcRenderer.on('lecturepack-production:message', listener);
    return () => ipcRenderer.removeListener('lecturepack-production:message', listener);
  }
});
