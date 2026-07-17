"""Windows Credential Manager storage for opt-in provider secrets.

Secrets deliberately never pass through ConfigManager or job JSON.  The
credential target contains no account identifier and the value is returned
only when an online request is about to start.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


GROQ_CREDENTIAL_TARGET = "LecturePack/Groq API Key"
_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2


class SecretStoreError(RuntimeError):
    pass


if os.name == "nt":
    class _CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]


class WindowsCredentialStore:
    """Minimal Credential Manager adapter with no plaintext fallback."""

    def __init__(self, target: str = GROQ_CREDENTIAL_TARGET):
        self.target = target

    def _api(self):
        if os.name != "nt":
            raise SecretStoreError("Windows Credential Manager is unavailable.")
        return ctypes.WinDLL("Advapi32.dll", use_last_error=True)

    def set(self, secret: str) -> None:
        value = str(secret or "").strip()
        if not value:
            raise SecretStoreError("API key cannot be empty.")
        raw = bytearray(value.encode("utf-16-le"))
        blob = (ctypes.c_ubyte * len(raw)).from_buffer(raw)
        cred = _CREDENTIALW()
        cred.Type = _CRED_TYPE_GENERIC
        cred.TargetName = self.target
        cred.CredentialBlobSize = len(raw)
        cred.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        cred.Persist = _CRED_PERSIST_LOCAL_MACHINE
        cred.UserName = "LecturePack"
        api = self._api()
        api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        try:
            if not api.CredWriteW(ctypes.byref(cred), 0):
                raise SecretStoreError(
                    f"Credential Manager write failed ({ctypes.get_last_error()}).")
        finally:
            for i in range(len(raw)):
                raw[i] = 0

    def get(self) -> str:
        api = self._api()
        ptr = ctypes.POINTER(_CREDENTIALW)()
        api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                  wintypes.DWORD,
                                  ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
        api.CredReadW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        if not api.CredReadW(self.target, _CRED_TYPE_GENERIC, 0,
                             ctypes.byref(ptr)):
            # ERROR_NOT_FOUND is normal and must not become a noisy exception.
            if ctypes.get_last_error() == 1168:
                return ""
            raise SecretStoreError(
                f"Credential Manager read failed ({ctypes.get_last_error()}).")
        try:
            cred = ptr.contents
            if not cred.CredentialBlob or not cred.CredentialBlobSize:
                return ""
            raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            return raw.decode("utf-16-le")
        finally:
            api.CredFree(ptr)

    def remove(self) -> bool:
        api = self._api()
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                    wintypes.DWORD]
        api.CredDeleteW.restype = wintypes.BOOL
        if api.CredDeleteW(self.target, _CRED_TYPE_GENERIC, 0):
            return True
        if ctypes.get_last_error() == 1168:
            return False
        raise SecretStoreError(
            f"Credential Manager delete failed ({ctypes.get_last_error()}).")

    def has_secret(self) -> bool:
        return bool(self.get())
