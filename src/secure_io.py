"""Local atomic writes: private staging files, explicit overwrite, no link following."""

import os
from pathlib import Path
import secrets
import stat
import tempfile


def validate_private_path(path: Path) -> Path:
    """Reject links and nonregular destinations; callers must trust the parent directory."""
    target = Path(os.path.abspath(path))
    for component in (target, *target.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        # st_file_attributes is available before Path.is_junction (Python 3.12).
        # Reject all Windows reparse points, including directory junctions on 3.10/3.11.
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise OSError("Linked paths are not supported for private files")
    if target.exists():
        info = target.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise OSError("Private file destination must be a regular, unlinked file")
    return target


def _create_windows_private_temp(parent: Path) -> tuple[int, str]:
    """Create the staging file with its protected DACL, with no inherited-access interval."""
    import ctypes
    from ctypes import wintypes
    import msvcrt

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p), ("bInheritHandle", wintypes.BOOL)]

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    advapi.GetSecurityDescriptorDacl.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL)]
    advapi.GetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    advapi.GetSecurityInfo.restype = wintypes.DWORD
    advapi.GetSecurityDescriptorControl.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD)]
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(SECURITY_ATTRIBUTES), wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p

    token = wintypes.HANDLE()
    sid_string = wintypes.LPWSTR()
    descriptor = ctypes.c_void_p()
    try:
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))  # TokenUser
        if not size.value:
            raise ctypes.WinError(ctypes.get_last_error())
        token_user = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, token_user, size, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        sid = ctypes.cast(token_user, ctypes.POINTER(ctypes.c_void_p))[0]
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(sid_string)):
            raise ctypes.WinError(ctypes.get_last_error())
        sddl = f"D:P(A;;FA;;;{sid_string.value})"
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
            raise ctypes.WinError(ctypes.get_last_error())
        present, defaulted = wintypes.BOOL(), wintypes.BOOL()
        dacl = ctypes.c_void_p()
        if not advapi.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)) or not present or not dacl:
            raise OSError("Could not construct private file ACL")
        attributes = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), descriptor, False)
        for _ in range(100):
            path = parent / f".aps-{secrets.token_hex(16)}.tmp"
            # CREATE_NEW, read/write, noninheritable handle, and private ACL at creation.
            handle = kernel.CreateFileW(str(path), 0xC0000000, 0x00000001, ctypes.byref(attributes), 1, 0x80, None)
            if handle == wintypes.HANDLE(-1).value:
                error = ctypes.get_last_error()
                if error in (80, 183):
                    continue
                raise ctypes.WinError(error)
            try:
                # Some filesystems accept creation while ignoring the descriptor.
                # Read back from the handle and fail before any secret is written.
                actual_descriptor, actual_dacl = ctypes.c_void_p(), ctypes.c_void_p()
                try:
                    error = advapi.GetSecurityInfo(handle, 1, 4, None, None, ctypes.byref(actual_dacl), None, ctypes.byref(actual_descriptor))
                    if error:
                        raise ctypes.WinError(error)
                    control, revision = wintypes.WORD(), wintypes.DWORD()
                    if not advapi.GetSecurityDescriptorControl(actual_descriptor, ctypes.byref(control), ctypes.byref(revision)):
                        raise ctypes.WinError(ctypes.get_last_error())
                    if not control.value & 0x1000 or not actual_dacl:
                        raise OSError("Private file DACL was not applied")
                    # ACL size is the WORD at offset two in the native ACL header.
                    expected_size = int.from_bytes(ctypes.string_at(dacl, 4)[2:4], "little")
                    actual_size = int.from_bytes(ctypes.string_at(actual_dacl, 4)[2:4], "little")
                    if actual_size != expected_size or ctypes.string_at(actual_dacl, actual_size) != ctypes.string_at(dacl, expected_size):
                        raise OSError("Private file DACL does not match")
                finally:
                    if actual_descriptor:
                        kernel.LocalFree(actual_descriptor)
                fd = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
            except BaseException:
                kernel.CloseHandle(handle)
                path.unlink(missing_ok=True)
                raise
            return fd, str(path)
        raise FileExistsError("Could not allocate private staging file")
    finally:
        if descriptor:
            kernel.LocalFree(descriptor)
        if sid_string:
            kernel.LocalFree(ctypes.cast(sid_string, ctypes.c_void_p))
        if token:
            kernel.CloseHandle(token)


def _restrict_fd(fd: int, path: Path) -> None:
    if os.name == "nt":
        # _create_windows_private_temp supplies the DACL to CreateFileW itself.
        return
    elif os.name == "posix":
        os.fchmod(fd, 0o600)
        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
            raise OSError("Could not restrict private file permissions")
    else:
        raise OSError("Private file permissions are unsupported on this platform")


def atomic_write_private(path: Path, text: str, *, overwrite: bool = True) -> None:
    """Stage privately in the target directory; publish only a complete file, or fail."""
    target = validate_private_path(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    validate_private_path(target)
    if not overwrite and target.exists():
        raise FileExistsError("Output already exists; explicit overwrite is required")
    if os.name == "nt":
        fd, name = _create_windows_private_temp(target.parent)
    else:
        fd, name = tempfile.mkstemp(prefix=".aps-", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        _restrict_fd(fd, temporary)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            fd = -1
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        validate_private_path(target)
        if overwrite:
            os.replace(temporary, target)
        else:
            # Atomic no-clobber publication, including a destination created after validation.
            os.link(temporary, target)
    finally:
        if fd != -1:
            os.close(fd)
        temporary.unlink(missing_ok=True)
