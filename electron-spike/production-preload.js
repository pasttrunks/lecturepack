'use strict';

const { contextBridge, ipcRenderer, webUtils } = require('electron');

// The production renderer receives only the narrow request/event surface. No
// Node, Electron, filesystem, or process handles cross the isolation boundary.
contextBridge.exposeInMainWorld('lecturePackElectron', {
  getAppVersion() {
    return ipcRenderer.invoke('lecturepack-production:version');
  },
  request(command, payload) {
    return ipcRenderer.invoke(
      'lecturepack-production:command',
      command,
      payload || {}
    );
  },
  getPathForFile(file) {
    return webUtils.getPathForFile(file);
  },
  onMessage(callback) {
    const listener = (_event, message) => callback(message);
    ipcRenderer.on('lecturepack-production:message', listener);
    return () => ipcRenderer.removeListener('lecturepack-production:message', listener);
  }
});
