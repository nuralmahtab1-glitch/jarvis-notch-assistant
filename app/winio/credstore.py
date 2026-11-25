"""API keys live in the Windows Credential Manager (encrypted by Windows for your account), never in a plain file.
Made by Nur Al Mahtab."""
from __future__ import annotations
import ctypes
from ctypes import wintypes as w

advapi = ctypes.windll.advapi32
CRED_TYPE_GENERIC, CRED_PERSIST_LOCAL_MACHINE = 1, 2
PREFIX = "Jarvis/"


class FILETIME(ctypes.Structure):
    _fields_ = [("lo", w.DWORD), ("hi", w.DWORD)]


class CREDENTIAL(ctypes.Structure):
    _fields_ = [("Flags", w.DWORD), ("Type", w.DWORD), ("TargetName", w.LPWSTR), ("Comment", w.LPWSTR),
                ("LastWritten", FILETIME), ("CredentialBlobSize", w.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", w.DWORD), ("AttributeCount", w.DWORD), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", w.LPWSTR), ("UserName", w.LPWSTR)]


advapi.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), w.DWORD]
advapi.CredReadW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
advapi.CredDeleteW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD]
advapi.CredFree.argtypes = [ctypes.c_void_p]


def save(name: str, secret: str, prefix: str = PREFIX) -> bool:
    blob = secret.encode("utf-16-le")
    buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    c = CREDENTIAL()
    c.Type, c.TargetName, c.UserName = CRED_TYPE_GENERIC, prefix + name, "Jarvis"
    c.CredentialBlobSize, c.CredentialBlob, c.Persist = len(blob), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)), CRED_PERSIST_LOCAL_MACHINE
    return bool(advapi.CredWriteW(ctypes.byref(c), 0))


def load(name: str, prefix: str = PREFIX) -> str:
    p = ctypes.POINTER(CREDENTIAL)()
    if not advapi.CredReadW(prefix + name, CRED_TYPE_GENERIC, 0, ctypes.byref(p)):
        return ""
    try:
        c = p.contents
        return ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize).decode("utf-16-le")
    finally:
        advapi.CredFree(p)


def delete(name: str, prefix: str = PREFIX) -> bool:
    return bool(advapi.CredDeleteW(prefix + name, CRED_TYPE_GENERIC, 0))
