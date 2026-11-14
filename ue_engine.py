"""
Unreal Engine 5.7.3 memory, reflection, AOB resolver, and x64 hook engine
for Spirit City: Lofi Sessions (SpiritCity-Win64-Shipping.exe).

Resolves GWorld, FNamePool, GUObjectArray, ProcessLocalScriptFunction, and
ProcessEvent dynamically via AOB scans and reflection — no hardcoded addresses.
"""

from __future__ import annotations

import ctypes
import os
import struct
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


# --- Win32 API Setup ---
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT_RESERVE = 0x3000
PAGE_EXECUTE_READWRITE = 0x40
TH32CS_SNAPPROCESS = 0x00000002
WAIT_TIMEOUT = 0x00000102
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
k32.Process32FirstW.restype = wintypes.BOOL
k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32NextW.restype = wintypes.BOOL
k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.CloseHandle.restype = wintypes.BOOL
k32.CloseHandle.argtypes = [wintypes.HANDLE]
k32.WaitForSingleObject.restype = wintypes.DWORD
k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
k32.ReadProcessMemory.restype = wintypes.BOOL
k32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
k32.WriteProcessMemory.restype = wintypes.BOOL
k32.WriteProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
k32.VirtualAllocEx.restype = ctypes.c_void_p
k32.VirtualAllocEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_size_t,
    wintypes.DWORD,
    wintypes.DWORD,
]
k32.VirtualProtectEx.restype = wintypes.BOOL
k32.VirtualProtectEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_size_t,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
k32.FlushInstructionCache.restype = wintypes.BOOL
k32.FlushInstructionCache.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t]
psapi.EnumProcessModulesEx.restype = wintypes.BOOL
psapi.EnumProcessModulesEx.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.HMODULE),
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.DWORD,
]


def find_pid(exe_name: str = "SpiritCity-Win64-Shipping.exe") -> Optional[int]:
    """Find the PID of a running process by executable name using Toolhelp32."""
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE or not snap:
        return None
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not k32.Process32FirstW(snap, ctypes.byref(pe)):
            return None
        target = exe_name.lower()
        while True:
            if pe.szExeFile.lower() == target:
                return int(pe.th32ProcessID)
            if not k32.Process32NextW(snap, ctypes.byref(pe)):
                break
    finally:
        k32.CloseHandle(snap)
    return None


def _aob_scan(text: bytes, base_addr: int, pat: str) -> int:
    """Fast AOB scan using longest literal byte-run + C-level bytes.find()."""
    mask = [None if p in ("?", "??") else int(p, 16) for p in pat.split()]
    best_start, best_len, cur_start = 0, 0, 0
    for i, val in enumerate(mask + [None]):
        if val is None:
            if i - cur_start > best_len:
                best_start, best_len = cur_start, i - cur_start
            cur_start = i + 1
    if best_len == 0:
        raise RuntimeError(f"Invalid AOB signature without literal bytes: {pat}")

    anchor = bytes(mask[best_start : best_start + best_len])  # type: ignore[arg-type]
    checks = [
        (i, val)
        for i, val in enumerate(mask)
        if val is not None and not (best_start <= i < best_start + best_len)
    ]
    total_len = len(mask)
    pos = 0
    while True:
        hit = text.find(anchor, pos)
        if hit < 0:
            break
        off = hit - best_start
        if 0 <= off and off + total_len <= len(text):
            if all(text[off + idx] == val for idx, val in checks):
                return base_addr + off
        pos = hit + 1
    raise RuntimeError(f"AOB signature not found: {pat}")


TOD_NAMES: Dict[int, str] = {0: "Morning", 1: "Day", 2: "Dusk", 3: "Night"}
LOC_NAMES: Dict[int, str] = {0: "Bedroom", 1: "Library", 2: "Train", 4: "Any Room", 5: "Garden"}
NOOK_NAMES: Dict[int, str] = {
    1: "Desk", 2: "Bed", 3: "Lounge Rug", 4: "Window Sill", 5: "Kitchen / Dining",
    6: "Train Front", 7: "Train Rear", 8: "Garden Patio", 9: "Greenhouse",
    10: "Garden Fountain", 11: "Library Armchair", 12: "Study Table",
    13: "Upper Mezzanine", 14: "Book Stacks",
}
ACT_NAMES: Dict[int, str] = {
    1: "Reading", 2: "Writing", 4: "Drawing", 5: "Gaming", 7: "Typing / Coding",
    8: "Knitting", 10: "Stretching", 13: "Cooking", 14: "Browsing", 16: "Tea / Coffee",
    17: "Cooking / Baking", 18: "Organizing", 19: "Picnicking", 20: "Eating", 21: "Plant Care",
    22: "Listening to Audio", 23: "Petting", 24: "Lounging / Napping", 25: "Gardening",
    26: "Potting", 27: "Crafting / Potions", 28: "Nature Watching", 29: "Foraging",
    30: "Inspecting Tomes", 31: "Researching", 32: "Lighting Candles", 33: "Incantations", 34: "Archiving",
}


@dataclass
class SpiritInfo:
    spirit_id: int
    code_name: str
    display_name: str
    discovered: bool
    luring: bool
    friendship: Optional[int]
    friendship_elem_addr: Optional[int]
    category: str = "Bedroom"
    required_tods: List[int] = field(default_factory=list)
    required_locs: List[int] = field(default_factory=list)
    required_rel_locs: List[int] = field(default_factory=list)
    required_acts: List[int] = field(default_factory=list)
    required_sounds: List[int] = field(default_factory=list)
    minutes: int = 0
    clues_summary: str = ""


@dataclass
class GameSnapshot:
    attached: bool
    pid: int = 0
    hook_installed: bool = False
    xp: int = 0
    level: int = 1
    credits: int = 0
    xp_progress_norm: float = 0.0
    xp_left_next: int = 0
    xp_next_threshold: int = 0
    daily_login_avail: bool = False
    daily_todo_avail: bool = False
    daily_pomo_avail: bool = False
    time_dilation: float = 1.0
    playtime_today_sec: int = 0
    train_speed: float = 0.0
    train_shake: float = 1.0
    time_of_day: int = 0
    sync_real_clock: bool = True
    parallax_strength: float = 20.0
    is_muted: bool = False
    is_ui_hidden: bool = False
    is_luring: bool = False
    discovered_count: int = 0
    total_spirits: int = 0
    pomo_state: int = 0
    pomo_loops: int = 0
    pomo_segment: int = 0
    timer_state: int = 0
    timer_passed: float = 0.0
    timer_length: float = 0.0
    stopwatch_state: int = 0
    stopwatch_passed: int = 0
    owned_packages: List[int] = field(default_factory=list)
    xp_calls: int = 0
    last_raw_xp: int = 0
    last_mult_xp: int = 0


class SpiritCityEngine:
    """Manages process attachment, UE5 reflection, and live hooks/commands."""

    # Cave control block layout (offsets from cave_base)
    OFF_XP_MULT = 0x00          # float32
    OFF_CR_MULT = 0x04          # float32
    OFF_XP_ENABLED = 0x08       # uint32
    OFF_CR_ENABLED = 0x0C       # uint32
    OFF_FREE_SHOP = 0x10        # uint32
    OFF_FAST_LURE = 0x14        # uint32
    OFF_FAST_LURE_SEC = 0x18    # float32
    OFF_FN_ADD_XP = 0x20        # uint64
    OFF_FN_ADD_CR = 0x28        # uint64
    OFF_FN_DEBIT_CR = 0x30      # uint64
    OFF_FN_CAN_BUY = 0x38       # uint64
    OFF_FN_START_LURE = 0x40    # uint64
    OFF_TOTAL_XP_CALLS = 0x48   # uint64
    OFF_LAST_RAW_XP = 0x50      # int32
    OFF_LAST_MULT_XP = 0x54     # int32
    OFF_FN_PROCESS_EVENT = 0x58 # uint64
    OFF_RETURN_ADDR = 0x60      # uint64
    OFF_CMD_STATE = 0x68        # uint32 (0=idle, 1=pending, 2=running)
    OFF_CMD_OBJ = 0x70          # uint64
    OFF_CMD_FN = 0x78           # uint64
    OFF_CMD_PARMS = 0x80        # 512 bytes (up to 0x280)

    ORIG_PLSF_BYTES = bytes.fromhex("48895c2420")

    def __init__(self) -> None:
        self.handle: Optional[int] = None
        self.pid: int = 0
        self.base: int = 0
        self._cmd_lock = threading.Lock()

        # Resolved engine addresses
        self.gworld_ptr: int = 0
        self.fname_pool_addr: int = 0
        self.gobj_addr: int = 0
        self.plsf_addr: int = 0
        self.pe_addr: int = 0

        # Cave state
        self.cave_addr: int = 0
        self.hook_installed: bool = False

        # Caches (cleared on detach or UWorld change)
        self._blocks: List[bytes] = []
        self._fname_cache: Dict[int, str] = {}
        self._prop_cache: Dict[Tuple[int, str], int] = {}
        self._fn_cache: Dict[Tuple[int, str], int] = {}
        self._cls_cache: Dict[int, int] = {}
        self._cached_world: int = 0
        self._cached_objs: Dict[str, int] = {}
        self._level_curve: List[Tuple[int, int]] = []
        self._fn_set_visibility: int = 0

    # --- Low-level Memory Helpers ---
    def is_alive(self) -> bool:
        return bool(self.handle and self.pid and k32.WaitForSingleObject(self.handle, 0) == WAIT_TIMEOUT)

    def rpm(self, addr: int, size: int) -> Optional[bytes]:
        if not self.handle or not addr or addr < 0x10000:
            return None
        buf = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(read)):
            return None
        return buf.raw[: read.value]

    def wpm(self, addr: int, data: bytes) -> bool:
        if not self.handle or not addr or addr < 0x10000:
            return False
        written = ctypes.c_size_t()
        ok = k32.WriteProcessMemory(self.handle, ctypes.c_void_p(addr), data, len(data), ctypes.byref(written))
        return bool(ok and written.value == len(data))

    def _read_fmt(self, addr: int, fmt: str, default: Any) -> Any:
        size = struct.calcsize(fmt)
        b = self.rpm(addr, size)
        return struct.unpack(fmt, b)[0] if b and len(b) == size else default

    def _write_fmt(self, addr: int, fmt: str, *vals: Any) -> bool:
        return self.wpm(addr, struct.pack("<" + fmt, *vals))

    def read_q(self, addr: int) -> int:
        return self._read_fmt(addr, "<Q", 0)

    def read_i(self, addr: int) -> int:
        return self._read_fmt(addr, "<i", 0)

    def read_u(self, addr: int) -> int:
        return self._read_fmt(addr, "<I", 0)

    def read_f(self, addr: int) -> float:
        return self._read_fmt(addr, "<f", 0.0)

    def read_d(self, addr: int) -> float:
        return self._read_fmt(addr, "<d", 0.0)

    def read_b(self, addr: int) -> int:
        return self._read_fmt(addr, "<B", 0)

    def read_fstr(self, addr: int) -> str:
        raw_hdr = self.rpm(addr, 16)
        if not raw_hdr or len(raw_hdr) < 16:
            return ""
        ptr, num, _ = struct.unpack("<QII", raw_hdr)
        return self._read_fstr_data(ptr, num)

    def _read_fstr_data(self, ptr: int, num: int) -> str:
        if not ptr or num <= 1 or num > 512:
            return ""
        raw = self.rpm(ptr, num * 2)
        return raw.decode("utf-16le", "replace").rstrip("\x00") if raw else ""

    def _patch_code(self, addr: int, data: bytes) -> None:
        old_p = wintypes.DWORD()
        k32.VirtualProtectEx(self.handle, ctypes.c_void_p(addr), len(data), PAGE_EXECUTE_READWRITE, ctypes.byref(old_p))
        self.wpm(addr, data)
        k32.VirtualProtectEx(self.handle, ctypes.c_void_p(addr), len(data), old_p.value, ctypes.byref(old_p))
        k32.FlushInstructionCache(self.handle, ctypes.c_void_p(addr), len(data))

    # --- Attach & Resolve ---
    def _parse_text_section(self) -> Tuple[int, int]:
        dos = self.rpm(self.base, 0x400)
        if not dos or dos[:2] != b"MZ":
            raise RuntimeError("Invalid PE header in target process.")
        e_lfanew = struct.unpack_from("<I", dos, 0x3C)[0]
        pe_hdr = self.rpm(self.base + e_lfanew, 0x300)
        if not pe_hdr or len(pe_hdr) < 0x100:
            raise RuntimeError("Failed to read PE header.")
        num_sec = struct.unpack_from("<H", pe_hdr, 6)[0]
        opt_size = struct.unpack_from("<H", pe_hdr, 20)[0]
        sec_off = 24 + opt_size
        for i in range(num_sec):
            s = sec_off + i * 40
            if s + 40 > len(pe_hdr):
                break
            name = pe_hdr[s : s + 8].rstrip(b"\x00").decode("ascii", "ignore")
            if name == ".text":
                text_vs, text_va = struct.unpack_from("<II", pe_hdr, s + 8)
                if text_va and text_vs:
                    return text_va, text_vs
        raise RuntimeError("Could not locate .text section.")

    def attach(self) -> None:
        self.detach()
        pid = find_pid()
        if not pid:
            raise RuntimeError("Spirit City: Lofi Sessions (SpiritCity-Win64-Shipping.exe) is not running.")
        h = k32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not h:
            raise RuntimeError(f"Failed to open game process (PID {pid}, err={ctypes.get_last_error()}). Try running as Administrator.")

        hmods = (wintypes.HMODULE * 1024)()
        cb = wintypes.DWORD()
        if not psapi.EnumProcessModulesEx(h, hmods, ctypes.sizeof(hmods), ctypes.byref(cb), 0x03):
            k32.CloseHandle(h)
            raise RuntimeError("Failed to enumerate process modules.")

        self.handle = h
        self.pid = pid
        self.base = int(hmods[0])

        try:
            text_va, text_vs = self._parse_text_section()
            text = self.rpm(self.base + text_va, text_vs)
            if not text:
                raise RuntimeError("Failed to read .text section from process.")

            text_base = self.base + text_va

            def resolve_rip(insn_addr: int, disp_off: int, insn_len: int) -> int:
                disp = struct.unpack_from("<i", text, (insn_addr - text_base) + disp_off)[0]
                return insn_addr + insn_len + disp

            self.gworld_ptr = resolve_rip(
                _aob_scan(text, text_base, "8B 40 30 48 85 C0 75 07 48 8B 05 ? ? ? ? C3 CC") + 8, 3, 7
            )
            self.fname_pool_addr = resolve_rip(
                _aob_scan(text, text_base, "74 09 4C 8D 3D ? ? ? ? EB 16 48 8D 0D") + 2, 3, 7
            )
            self.gobj_addr = resolve_rip(
                _aob_scan(text, text_base, "48 C7 41 10 00 00 00 00 48 8D 05 ? ? ? ? 48 89 01 B8 FF FF FF FF") + 8,
                3,
                7,
            )
            # Scan post-prologue bytes so recovery works even if an earlier E9 hook remains
            self.plsf_addr = (
                _aob_scan(
                    text,
                    text_base,
                    "56 57 41 56 48 83 EC 70 48 8B 05 ? ? ? ? 48 33 C4 48 89 44 24 60 48 8B 42 20 4C 8D 35",
                )
                - 5
            )

            world = self.read_q(self.gworld_ptr)
            if not world:
                raise RuntimeError("Game world is still loading — please wait a few seconds and retry.")

            world_vt = self.read_q(world)
            self.pe_addr = self.read_q(world_vt + 76 * 8)

            self._load_fname_pool()
            self._resolve_curve_and_widget_fn()
            self._install_hook()
        except Exception:
            self.detach()
            raise

    def detach(self) -> None:
        if self.handle:
            if self.hook_installed and self.plsf_addr:
                try:
                    self._uninstall_hook()
                except Exception:
                    pass
            k32.CloseHandle(self.handle)
        self.handle = None
        self.pid = 0
        self.base = 0
        self.cave_addr = 0
        self.hook_installed = False
        self._blocks.clear()
        self._fname_cache.clear()
        self._prop_cache.clear()
        self._fn_cache.clear()
        self._cls_cache.clear()
        self._cached_world = 0
        self._cached_objs.clear()
        self._level_curve.clear()
        self._fn_set_visibility = 0

    # --- UE5 Reflection Helpers ---
    def _load_fname_pool(self) -> None:
        hdr = self.rpm(self.fname_pool_addr + 8, 8)
        if not hdr or len(hdr) < 8:
            raise RuntimeError("Failed to read FNamePool header.")
        cur_block, cur_cursor = struct.unpack("<II", hdr)
        ptrs_raw = self.rpm(self.fname_pool_addr + 0x10, (cur_block + 1) * 8)
        if not ptrs_raw:
            raise RuntimeError("Failed to read FNamePool blocks.")
        blocks_ptrs = struct.unpack(f"<{cur_block + 1}Q", ptrs_raw)
        self._blocks = [
            self.rpm(bp, cur_cursor if i == cur_block else 0x20000) or b"" for i, bp in enumerate(blocks_ptrs)
        ]
        self._fname_cache.clear()

    def get_fname(self, idx: int) -> str:
        cached = self._fname_cache.get(idx)
        if cached is not None:
            return cached
        blk = idx >> 16
        off = (idx & 0xFFFF) * 2
        if blk >= len(self._blocks) or off + 2 > len(self._blocks[blk]):
            return ""
        hdr = struct.unpack_from("<H", self._blocks[blk], off)[0]
        is_wide = hdr & 1
        length = hdr >> 6
        raw = self._blocks[blk][off + 2 : off + 2 + length * (2 if is_wide else 1)]
        s = raw.decode("utf-16le" if is_wide else "utf-8", "replace")
        self._fname_cache[idx] = s
        return s

    def get_obj_name(self, ptr: int) -> str:
        if not ptr:
            return ""
        hdr = self.rpm(ptr, 0x28)
        if not hdr or len(hdr) < 0x28:
            return ""
        _, _, _, _, n_idx, n_num, _ = struct.unpack_from("<QIIQIIQ", hdr, 0)
        n = self.get_fname(n_idx)
        return f"{n}_{n_num - 1}" if n_num > 0 else n

    def _obj_cls(self, obj: int) -> int:
        cls_ptr = self._cls_cache.get(obj)
        if not cls_ptr:
            cls_ptr = self.read_q(obj + 0x10)
            if cls_ptr:
                self._cls_cache[obj] = cls_ptr
        return cls_ptr

    def get_prop_offset(self, cls_ptr: int, prop_name: str) -> int:
        key = (cls_ptr, prop_name)
        cached = self._prop_cache.get(key)
        if cached is not None:
            return cached
        cur = cls_ptr
        for _ in range(12):
            if not cur:
                break
            prop = self.read_q(cur + 0x50)
            while prop:
                raw = self.rpm(prop, 0x50)
                if not raw or len(raw) < 0x48:
                    break
                next_ptr = struct.unpack_from("<Q", raw, 0x18)[0]
                n_idx, n_num = struct.unpack_from("<II", raw, 0x20)
                pname = self.get_fname(n_idx)
                if n_num > 0:
                    pname = f"{pname}_{n_num - 1}"
                if pname == prop_name:
                    off = struct.unpack_from("<i", raw, 0x44)[0]
                    self._prop_cache[key] = off
                    return off
                prop = next_ptr
            cur = self.read_q(cur + 0x40)
        raise KeyError(f"Property '{prop_name}' not found on class 0x{cls_ptr:X}")

    def get_func(self, cls_ptr: int, func_name: str) -> int:
        key = (cls_ptr, func_name)
        cached = self._fn_cache.get(key)
        if cached is not None:
            return cached
        cur = cls_ptr
        for _ in range(12):
            if not cur:
                break
            ch = self.read_q(cur + 0x48)
            while ch:
                if self.get_obj_name(ch) == func_name:
                    self._fn_cache[key] = ch
                    return ch
                ch = self.read_q(ch + 0x28)
            cur = self.read_q(cur + 0x40)
        raise KeyError(f"Function '{func_name}' not found on class 0x{cls_ptr:X}")

    def _read_props(self, obj: int, specs: Sequence[Tuple[str, str]]) -> Tuple[Any, ...]:
        """Batch-read reflected properties from one UObject in a single RPM when close."""
        cls_ptr = self._obj_cls(obj)
        resolved = [(self.get_prop_offset(cls_ptr, name), "<" + fmt) for name, fmt in specs]
        lo = min(off for off, _ in resolved)
        hi = max(off + struct.calcsize(fmt) for off, fmt in resolved)
        if hi - lo <= 4096:
            buf = self.rpm(obj + lo, hi - lo)
            if buf and len(buf) == hi - lo:
                return tuple(struct.unpack_from(fmt, buf, off - lo)[0] for off, fmt in resolved)
        return tuple(self._read_fmt(obj + off, fmt, 0) for off, fmt in resolved)

    def _write_prop(self, obj: int, prop_name: str, fmt: str, val: Any) -> bool:
        off = self.get_prop_offset(self._obj_cls(obj), prop_name)
        return self._write_fmt(obj + off, fmt, val)

    def _call_named(self, obj: int, fn_name: str, parms: bytes = b"", timeout_s: float = 2.0) -> bytes:
        fn = self.get_func(self._obj_cls(obj), fn_name)
        return self.call_ufunction(obj, fn, parms, timeout_s=timeout_s)

    def _read_tarray_hdr(self, addr: int) -> Tuple[int, int, int]:
        raw = self.rpm(addr, 16)
        if not raw or len(raw) < 16:
            return 0, 0, 0
        return struct.unpack("<QII", raw)

    # --- Core Object Graph Pointers (World-Keyed Cache) ---
    def get_world(self) -> int:
        w = self.read_q(self.gworld_ptr)
        if w != self._cached_world:
            self._cached_world = w
            self._cached_objs.clear()
            self._cls_cache.clear()
        return w

    def _cached_ptr(self, key: str, resolver) -> int:
        self.get_world()
        val = self._cached_objs.get(key)
        if val:
            return val
        val = resolver()
        if val:
            self._cached_objs[key] = val
        return val

    def get_game_instance(self) -> int:
        return self._cached_ptr("gi", lambda: self.read_q(self._cached_world + 0x228) if self._cached_world else 0)

    def get_pc(self) -> int:
        def _resolve() -> int:
            gi = self.get_game_instance()
            if not gi:
                return 0
            lp_arr = self.read_q(gi + 0x038)
            lp = self.read_q(lp_arr) if lp_arr else 0
            return self.read_q(lp + 0x30) if lp else 0

        return self._cached_ptr("pc", _resolve)

    def get_world_settings(self) -> int:
        def _resolve() -> int:
            w = self._cached_world
            lvl = self.read_q(w + 0x030) if w else 0
            return self.read_q(lvl + 0x2B0) if lvl else 0

        return self._cached_ptr("ws", _resolve)

    def _get_pc_ref(self, prop_name: str) -> int:
        def _resolve() -> int:
            pc = self.get_pc()
            if not pc:
                return 0
            return self.read_q(pc + self.get_prop_offset(self._obj_cls(pc), prop_name))

        return self._cached_ptr(prop_name, _resolve)

    def get_hud(self) -> int:
        return self._get_pc_ref("REF HUD")

    def get_sim(self) -> int:
        return self._get_pc_ref("REF_SpiritInteractionManager")

    def get_tod_mgr(self) -> int:
        return self._get_pc_ref("REF_TimeOfDayManager")

    def get_prod_mgr(self) -> int:
        return self._get_pc_ref("REF_ProductivityManager")

    def _resolve_curve_and_widget_fn(self) -> None:
        pc = self.get_pc()
        if not pc:
            return
        curve = self.read_q(pc + self.get_prop_offset(self._obj_cls(pc), "REF_LevelUpCurveData"))
        if curve:
            keys_ptr, keys_num, _ = self._read_tarray_hdr(curve + 0xA0)
            if keys_ptr and 0 < keys_num < 500:
                k_all = self.rpm(keys_ptr, keys_num * 28)
                if k_all and len(k_all) >= keys_num * 28:
                    self._level_curve = sorted(
                        (
                            (int(round(t)), int(round(v)))
                            for t, v in (struct.unpack_from("<ff", k_all, i * 28 + 4) for i in range(keys_num))
                        ),
                        key=lambda pair: pair[0],
                    )

        hud = self.get_hud()
        if hud:
            cheat_menu = self.read_q(hud + self.get_prop_offset(self._obj_cls(hud), "WBP_CheatMenu"))
            if cheat_menu:
                self._fn_set_visibility = self.get_func(self._obj_cls(cheat_menu), "SetVisibility")

    # --- x64 Code Cave Installation ---
    def _alloc_near(self, target_addr: int, size: int = 4096) -> int:
        for delta in range(0x10000, 0x70000000, 0x10000):
            for cand in (target_addr - delta, target_addr + delta):
                if cand < 0x10000000:
                    continue
                p = k32.VirtualAllocEx(self.handle, ctypes.c_void_p(cand), size, MEM_COMMIT_RESERVE, PAGE_EXECUTE_READWRITE)
                if p and abs(p - target_addr) < 0x7FFF0000:
                    return int(p)
        raise RuntimeError("Failed to allocate RWX cave within +/-2GB of target.")

    def _install_hook(self) -> None:
        cur_bytes = self.rpm(self.plsf_addr, 5)
        if cur_bytes != self.ORIG_PLSF_BYTES:
            if cur_bytes and cur_bytes[0] == 0xE9:
                # Recover cleanly if a previous session crashed before detaching
                self._patch_code(self.plsf_addr, self.ORIG_PLSF_BYTES)
                time.sleep(0.05)
            else:
                raise RuntimeError(
                    f"Unexpected prologue bytes at ProcessLocalScriptFunction: {cur_bytes.hex() if cur_bytes else None}"
                )

        pc = self.get_pc()
        sim = self.get_sim()
        pc_cls = self._obj_cls(pc)
        sim_cls = self._obj_cls(sim)

        fn_add_xp = self.get_func(pc_cls, "Add XP")
        fn_add_cr = self.get_func(pc_cls, "Add Spirit Credits")
        fn_deb_cr = self.get_func(pc_cls, "Debit Spirit Credits")
        fn_can_buy = self.get_func(pc_cls, "Check if can buy item")
        fn_start_lure = self.get_func(sim_cls, "StartSpiritLuringTimer")

        cave = self._alloc_near(self.plsf_addr, 4096)
        data_block = bytearray(0x300)
        struct.pack_into("<ffIIIIfI", data_block, 0x00, 1.0, 1.0, 1, 0, 0, 0, 0.05, 0)
        struct.pack_into("<QQQQQ", data_block, 0x20, fn_add_xp, fn_add_cr, fn_deb_cr, fn_can_buy, fn_start_lure)
        struct.pack_into("<QiiQQ", data_block, 0x48, 0, 0, 0, self.pe_addr, self.plsf_addr + 5)
        self.wpm(cave, bytes(data_block))

        code_base = cave + 0x300
        buf = bytearray()
        labels: Dict[str, int] = {}
        fixups: List[Tuple[int, Any, bool]] = []

        def emit(b: bytes) -> None:
            buf.extend(b)

        def label(name: str) -> None:
            labels[name] = len(buf)

        def rip_data(off: int) -> None:
            fixups.append((len(buf), cave + off, True))
            emit(b"\x00\x00\x00\x00")

        def jcc32(op2: bytes, name: str) -> None:
            emit(op2)
            fixups.append((len(buf), name, False))
            emit(b"\x00\x00\x00\x00")

        def jmp32(name: str) -> None:
            emit(b"\xe9")
            fixups.append((len(buf), name, False))
            emit(b"\x00\x00\x00\x00")

        # Entry: rcx=Context, rdx=Stack, r8=Result
        emit(b"\x4c\x8b\x4a\x10\x4c\x8b\x52\x28\x4d\x85\xd2")  # mov r9,[rdx+10]; mov r10,[rdx+28]; test r10,r10
        jcc32(b"\x0f\x84", "check_cmd")

        # 1) Add XP Multiplier
        emit(b"\x4c\x3b\x0d")
        rip_data(self.OFF_FN_ADD_XP)
        jcc32(b"\x0f\x85", "check_add_credits")
        emit(b"\x48\xff\x05")
        rip_data(self.OFF_TOTAL_XP_CALLS)
        emit(b"\x41\x8b\x02\x89\x05")
        rip_data(self.OFF_LAST_RAW_XP)
        emit(b"\x44\x8b\x1d")
        rip_data(self.OFF_XP_ENABLED)
        emit(b"\x45\x85\xdb")
        jcc32(b"\x0f\x84", "xp_store_done")
        emit(b"\x85\xc0")
        jcc32(b"\x0f\x8e", "xp_store_done")
        emit(b"\xf3\x0f\x2a\xc0\xf3\x0f\x10\x0d")
        rip_data(self.OFF_XP_MULT)
        emit(b"\xf3\x0f\x59\xc1\xf3\x0f\x2c\xc0\x85\xc0")
        jcc32(b"\x0f\x8f", "xp_write")
        emit(b"\x0f\x57\xc0\x0f\x2e\xc8")
        jcc32(b"\x0f\x86", "xp_write")
        emit(b"\xb8\x01\x00\x00\x00")
        label("xp_write")
        emit(b"\x41\x89\x02")
        label("xp_store_done")
        emit(b"\x89\x05")
        rip_data(self.OFF_LAST_MULT_XP)
        jmp32("check_cmd")

        # 2) Add Spirit Credits Multiplier
        label("check_add_credits")
        emit(b"\x4c\x3b\x0d")
        rip_data(self.OFF_FN_ADD_CR)
        jcc32(b"\x0f\x85", "check_debit")
        emit(b"\x44\x8b\x1d")
        rip_data(self.OFF_CR_ENABLED)
        emit(b"\x45\x85\xdb")
        jcc32(b"\x0f\x84", "check_cmd")
        emit(b"\x41\x8b\x02\x85\xc0")
        jcc32(b"\x0f\x8e", "check_cmd")
        emit(b"\xf3\x0f\x2a\xc0\xf3\x0f\x10\x0d")
        rip_data(self.OFF_CR_MULT)
        emit(b"\xf3\x0f\x59\xc1\xf3\x0f\x2c\xc0\x41\x89\x02")
        jmp32("check_cmd")

        # 3) Free Shop (Debit Spirit Credits & Check if can buy item)
        label("check_debit")
        emit(b"\x4c\x3b\x0d")
        rip_data(self.OFF_FN_DEBIT_CR)
        jcc32(b"\x0f\x84", "do_free_shop")
        emit(b"\x4c\x3b\x0d")
        rip_data(self.OFF_FN_CAN_BUY)
        jcc32(b"\x0f\x85", "check_lure")
        label("do_free_shop")
        emit(b"\x44\x8b\x1d")
        rip_data(self.OFF_FREE_SHOP)
        emit(b"\x45\x85\xdb")
        jcc32(b"\x0f\x84", "check_cmd")
        emit(b"\x41\xc7\x02\x00\x00\x00\x00")
        jmp32("check_cmd")

        # 4) Fast Spirit Luring (StartSpiritLuringTimer)
        label("check_lure")
        emit(b"\x4c\x3b\x0d")
        rip_data(self.OFF_FN_START_LURE)
        jcc32(b"\x0f\x85", "check_cmd")
        emit(b"\x44\x8b\x1d")
        rip_data(self.OFF_FAST_LURE)
        emit(b"\x45\x85\xdb")
        jcc32(b"\x0f\x84", "check_cmd")
        emit(b"\x8b\x05")
        rip_data(self.OFF_FAST_LURE_SEC)
        emit(b"\x41\x89\x02")

        # 5) Game-Thread ProcessEvent Command Executor
        label("check_cmd")
        emit(b"\x8b\x05")
        rip_data(self.OFF_CMD_STATE)
        emit(b"\x83\xf8\x01")
        jcc32(b"\x0f\x85", "orig")
        emit(b"\xb8\x02\x00\x00\x00\xf0\x87\x05")
        rip_data(self.OFF_CMD_STATE)
        emit(b"\x83\xf8\x01")
        jcc32(b"\x0f\x85", "orig")
        emit(b"\x51\x52\x41\x50\x41\x51\x48\x83\xec\x28")
        emit(b"\x48\x8b\x0d")
        rip_data(self.OFF_CMD_OBJ)
        emit(b"\x48\x8b\x15")
        rip_data(self.OFF_CMD_FN)
        emit(b"\x4c\x8d\x05")
        rip_data(self.OFF_CMD_PARMS)
        emit(b"\xff\x15")
        rip_data(self.OFF_FN_PROCESS_EVENT)
        emit(b"\x48\x83\xc4\x28\x41\x59\x41\x58\x5a\x59\x33\xc0\x89\x05")
        rip_data(self.OFF_CMD_STATE)

        # 6) Stolen instruction + jump back
        label("orig")
        emit(self.ORIG_PLSF_BYTES)
        emit(b"\xff\x25")
        rip_data(self.OFF_RETURN_ADDR)

        for pos, target, is_abs in fixups:
            if is_abs:
                struct.pack_into("<i", buf, pos, target - (code_base + pos + 4))
            else:
                struct.pack_into("<i", buf, pos, labels[target] - (pos + 4))

        self.wpm(code_base, bytes(buf))
        self._patch_code(self.plsf_addr, b"\xe9" + struct.pack("<i", code_base - (self.plsf_addr + 5)))

        self.cave_addr = cave
        self.hook_installed = True

    def _uninstall_hook(self) -> None:
        if not self.hook_installed or not self.plsf_addr:
            return
        self._patch_code(self.plsf_addr, self.ORIG_PLSF_BYTES)
        self.hook_installed = False

    # --- Game-Thread UFunction Execution ---
    def call_ufunction(self, obj_ptr: int, fn_ptr: int, parms: bytes = b"", timeout_s: float = 1.5) -> bytes:
        if not self.hook_installed or not self.cave_addr:
            raise RuntimeError("Hook not installed.")
        if not obj_ptr or not fn_ptr:
            raise RuntimeError("Invalid target object or UFunction pointer.")

        with self._cmd_lock:
            self.wpm(self.cave_addr + self.OFF_CMD_PARMS, parms.ljust(512, b"\x00")[:512])
            self._write_fmt(self.cave_addr + self.OFF_CMD_OBJ, "QQ", obj_ptr, fn_ptr)
            self._write_fmt(self.cave_addr + self.OFF_CMD_STATE, "I", 1)

            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                if self.read_u(self.cave_addr + self.OFF_CMD_STATE) == 0:
                    return self.rpm(self.cave_addr + self.OFF_CMD_PARMS, 512) or b""
                time.sleep(0.01)

            self._write_fmt(self.cave_addr + self.OFF_CMD_STATE, "I", 0)
            raise TimeoutError("Game-thread UFunction call timed out (is the game frozen or minimized?).")

    def _call_bypassing_flag(self, obj: int, fn_name: str, parms: bytes, flag_off: int, bypass: bool) -> None:
        fn = self.get_func(self._obj_cls(obj), fn_name)
        was_enabled = self.read_u(self.cave_addr + flag_off) if bypass else 0
        if bypass:
            self._write_fmt(self.cave_addr + flag_off, "I", 0)
        try:
            self.call_ufunction(obj, fn, parms)
        finally:
            if bypass:
                self._write_fmt(self.cave_addr + flag_off, "I", was_enabled)

    # --- Hook Config Setters ---
    def set_xp_multiplier(self, enabled: bool, mult: float) -> None:
        if self.cave_addr:
            self._write_fmt(self.cave_addr + self.OFF_XP_MULT, "f", max(0.0, float(mult)))
            self._write_fmt(self.cave_addr + self.OFF_XP_ENABLED, "I", int(enabled))

    def set_credits_multiplier(self, enabled: bool, mult: float) -> None:
        if self.cave_addr:
            self._write_fmt(self.cave_addr + self.OFF_CR_MULT, "f", max(0.0, float(mult)))
            self._write_fmt(self.cave_addr + self.OFF_CR_ENABLED, "I", int(enabled))

    def set_free_shop(self, enabled: bool) -> None:
        if self.cave_addr:
            self._write_fmt(self.cave_addr + self.OFF_FREE_SHOP, "I", int(enabled))

    def set_fast_lure(self, enabled: bool, interval_sec: float = 0.05) -> None:
        if self.cave_addr:
            self._write_fmt(
                self.cave_addr + self.OFF_FAST_LURE,
                "If",
                int(enabled),
                max(0.01, float(interval_sec)),
            )

    # --- Progression Helpers ---
    def _calc_level_progress(self, total_xp: int, current_lvl: int) -> Tuple[float, int, int]:
        if not self._level_curve:
            return 0.0, 0, 0
        cur_thresh = next_thresh = 0
        for lvl, xp_val in self._level_curve:
            if lvl <= current_lvl:
                cur_thresh = xp_val
            if lvl >= current_lvl + 1:
                next_thresh = xp_val
                break
        if next_thresh <= cur_thresh:
            return 1.0, 0, next_thresh
        span = next_thresh - cur_thresh
        done = max(0, total_xp - cur_thresh)
        return min(1.0, done / span), max(0, next_thresh - total_xp), next_thresh

    def _xp_for_level(self, target_lvl: int) -> Optional[int]:
        if not self._level_curve:
            return None
        prev_l, prev_x = self._level_curve[0]
        if target_lvl <= prev_l:
            return prev_x
        for lvl, xp_val in self._level_curve[1:]:
            if lvl >= target_lvl:
                ratio = (target_lvl - prev_l) / max(1, lvl - prev_l)
                return int(round(prev_x + ratio * (xp_val - prev_x)))
            prev_l, prev_x = lvl, xp_val
        return self._level_curve[-1][1]

    def add_xp(self, amount: int, notify: bool = True, bypass_multiplier: bool = False) -> None:
        if pc := self.get_pc():
            self._call_bypassing_flag(
                pc, "Add XP", struct.pack("<iB", int(amount), int(notify)), self.OFF_XP_ENABLED, bypass_multiplier
            )

    def add_credits(self, amount: int, bypass_multiplier: bool = False) -> None:
        if pc := self.get_pc():
            self._call_bypassing_flag(
                pc, "Add Spirit Credits", struct.pack("<i", int(amount)), self.OFF_CR_ENABLED, bypass_multiplier
            )

    def set_xp(self, new_xp: int) -> None:
        if pc := self.get_pc():
            self._write_prop(pc, "Total Cumulative XP", "i", max(0, int(new_xp)))
            self.add_xp(0, notify=False, bypass_multiplier=True)

    def set_level(self, new_lvl: int, sync_xp: bool = True) -> None:
        pc = self.get_pc()
        if not pc:
            return
        lvl_int = max(1, int(new_lvl))
        self._write_prop(pc, "Current LVL", "i", lvl_int)
        if sync_xp and (target_xp := self._xp_for_level(lvl_int)) is not None:
            self._write_prop(pc, "Total Cumulative XP", "i", target_xp)
        self.add_xp(0, notify=False, bypass_multiplier=True)

    def set_credits(self, new_credits: int) -> None:
        if pc := self.get_pc():
            self._write_prop(pc, "Current Spirit Credits", "i", max(0, int(new_credits)))
            self.add_credits(0, bypass_multiplier=True)

    def trigger_level_up(self) -> None:
        if pc := self.get_pc():
            self._call_named(pc, "LevelUp")

    def trigger_save(self) -> None:
        if pc := self.get_pc():
            try:
                self._call_named(pc, "TriggerSave")
            except Exception:
                pass
        if sim := self.get_sim():
            try:
                self._call_named(sim, "Trigger Save")
                self._call_named(sim, "Save")
            except Exception:
                pass

    def set_daily_bonuses_available(self, login: bool = True, todo: bool = True, pomo: bool = True) -> None:
        if pc := self.get_pc():
            self._write_prop(pc, "canEarnDailyEXP_Login", "B", int(login))
            self._write_prop(pc, "canEarnDailyEXP_Todo", "B", int(todo))
            self._write_prop(pc, "canEarnDailyEXP_Pomo", "B", int(pomo))

    # --- World, Speed, Time of Day, Train, Audio, UI ---
    def set_game_speed(self, speed: float) -> None:
        if ws := self.get_world_settings():
            self._write_prop(ws, "TimeDilation", "f", max(0.05, float(speed)))

    def set_time_of_day(self, scenario: int, sync_real_clock: bool = False) -> None:
        if tod := self.get_tod_mgr():
            self._write_prop(tod, "Play with real life clock (or play with set lighting)", "B", int(sync_real_clock))
            self._call_named(tod, "UI_TriggerNewTimeOfDay", struct.pack("<B", int(scenario) & 0xFF))

    def set_train_params(self, speed: Optional[float] = None, shake: Optional[float] = None) -> None:
        prod = self.get_prod_mgr()
        if not prod:
            return
        if speed is not None:
            self._call_named(prod, "UpdateTrainSpeed", struct.pack("<d", float(speed)))
        if shake is not None:
            self._call_named(prod, "UpdateTrainShake", struct.pack("<d", float(shake)))

    def set_playtime_today(self, seconds: int) -> None:
        if prod := self.get_prod_mgr():
            self._write_prop(prod, "PlaytimeToday", "i", max(0, int(seconds)))

    def set_parallax_strength(self, strength: float) -> None:
        if pc := self.get_pc():
            self._write_prop(pc, "Parallax Effect Strength", "d", float(strength))

    def set_mute(self, muted: bool) -> None:
        if hud := self.get_hud():
            self._write_prop(hud, "isMuted", "B", int(muted))

    def set_ui_hidden(self, hidden: bool) -> None:
        if hud := self.get_hud():
            self._write_prop(hud, "isUIHidden", "B", int(hidden))

    # --- Pomodoro / Timer / Stopwatch ---
    def _get_pomodoro_widgets(self) -> Tuple[int, int, int, int]:
        hud = self.get_hud()
        if not hud:
            return 0, 0, 0, 0
        pm = self._cached_ptr("pm", lambda: self.read_q(hud + self.get_prop_offset(self._obj_cls(hud), "UI_PomodoroV2")))
        if not pm:
            return 0, 0, 0, 0
        p_v2, p_tmr, p_sw = self._read_props(
            pm, (("WBP_PomodoroV2", "Q"), ("WBP_PomodoroV2_Timer", "Q"), ("WBP_PomodoroV2_Stopwatch", "Q"))
        )
        return pm, p_v2, p_tmr, p_sw

    def complete_active_timer(self) -> str:
        _, p_v2, p_tmr, _ = self._get_pomodoro_widgets()
        if p_tmr:
            st, tlen = self._read_props(p_tmr, (("State", "B"), ("TimerLength", "d")))
            if st == 1:
                self._write_prop(p_tmr, "TimePassed", "d", max(0.0, tlen - 0.5))
                return "Timer set to finish in ~1s!"

        if p_v2:
            st, seg_idx = self._read_props(p_v2, (("State", "B"), ("CurrentSegment", "i")))
            if st == 1:
                res = self._call_named(p_v2, "GetSegmentAtIndex", struct.pack("<i", seg_idx))
                seg_obj, ok = struct.unpack_from("<QB", res, 8)
                if ok and seg_obj:
                    tlen = self.read_d(seg_obj + self.get_prop_offset(self._obj_cls(seg_obj), "TimerLength"))
                    self._write_prop(seg_obj, "TimePassed", "d", max(0.0, tlen - 0.5))
                    return f"Pomodoro segment #{seg_idx + 1} set to finish in ~1s!"
        return "No active running Timer or Pomodoro session detected."

    def set_stopwatch_seconds(self, seconds: int) -> None:
        _, _, _, p_sw = self._get_pomodoro_widgets()
        if p_sw:
            self._write_prop(p_sw, "TimePassed", "i", max(0, int(seconds)))

    # --- Spirits & Friendship ---
    def apply_lure_timer_now(self, interval_sec: float = 0.05) -> None:
        if sim := self.get_sim():
            self._call_named(sim, "StartSpiritLuringTimer", struct.pack("<f", max(0.01, float(interval_sec))))

    @staticmethod
    def _get_spiritdex_sav_path() -> str:
        return os.path.expandvars(r"%LOCALAPPDATA%\SpiritCity\Saved\SaveGames\SCLS_Spiritdex.sav")

    def _read_spiritdex_file(self) -> Tuple[List[int], Dict[int, int]]:
        path = self._get_spiritdex_sav_path()
        if not os.path.isfile(path):
            return [], {}
        try:
            with open(path, "rb") as f:
                data = f.read()

            disc_ids: List[int] = []
            tag_disc = b"\x16\x00\x00\x00Spirit IDs discovered\x00"
            idx_disc = data.find(tag_disc)
            if idx_disc != -1:
                # 26 (name) + 18 (ArrayProperty) + 4 (01 00 00 00) + 16 (IntProperty) + 4 (index) = 68
                pos = idx_disc + 68
                count = struct.unpack_from("<I", data, pos + 5)[0]
                disc_ids = list(struct.unpack(f"<{count}i", data[pos + 9 : pos + 9 + count * 4]))

            friendships: Dict[int, int] = {}
            tag_friend = b"\x1f\x00\x00\x00Spirit IDs to Friendship score\x00"
            idx_friend = data.find(tag_friend)
            if idx_friend != -1:
                # 35 (name) + 16 (MapProperty) + 4 (02) + 20 (IntProperty+trailer) + 20 (IntProperty+trailer) = 95
                pos = idx_friend + 95
                count = struct.unpack_from("<I", data, pos + 9)[0]
                for i in range(count):
                    k, v = struct.unpack_from("<ii", data, pos + 13 + i * 8)
                    friendships[k] = v

            return disc_ids, friendships
        except Exception:
            return [], {}

    def _save_spiritdex_file(self, discovered_ids: List[int], friendship_map: Dict[int, int]) -> bool:
        path = self._get_spiritdex_sav_path()
        if not os.path.isfile(path):
            return False
        try:
            with open(path, "rb") as f:
                data = f.read()

            tag_disc = b"\x16\x00\x00\x00Spirit IDs discovered\x00"
            idx_disc = data.find(tag_disc)
            if idx_disc == -1:
                return False

            prefix = data[:idx_disc]

            # 1. Spirit IDs discovered
            p_disc = bytearray()
            p_disc += b"\x16\x00\x00\x00Spirit IDs discovered\x00"
            p_disc += b"\x0e\x00\x00\x00ArrayProperty\x00"
            p_disc += b"\x01\x00\x00\x00"
            p_disc += b"\x0c\x00\x00\x00IntProperty\x00"
            p_disc += b"\x00\x00\x00\x00"

            num_disc = len(discovered_ids)
            tag_size_disc = 4 + num_disc * 4
            p_disc += struct.pack("<IBI", tag_size_disc, 0, num_disc)
            for sid in discovered_ids:
                p_disc += struct.pack("<i", sid)

            # 2. Spirit IDs to Friendship score
            p_friend = bytearray()
            p_friend += b"\x1f\x00\x00\x00Spirit IDs to Friendship score\x00"
            p_friend += b"\x0c\x00\x00\x00MapProperty\x00"
            p_friend += b"\x02\x00\x00\x00"
            p_friend += b"\x0c\x00\x00\x00IntProperty\x00\x00\x00\x00\x00"
            p_friend += b"\x0c\x00\x00\x00IntProperty\x00\x00\x00\x00\x00"

            num_friend = len(friendship_map)
            tag_size_friend = 4 + 4 + num_friend * 8
            p_friend += struct.pack("<IBII", tag_size_friend, 0, 0, num_friend)
            for sid, score in friendship_map.items():
                p_friend += struct.pack("<ii", sid, score)

            # 3. Terminator
            terminator = b"\x05\x00\x00\x00None\x00\x00\x00\x00\x00"

            new_data = bytes(prefix) + bytes(p_disc) + bytes(p_friend) + terminator
            with open(path, "wb") as f:
                f.write(new_data)
            return True
        except Exception:
            return False

    def get_room_state(self) -> Dict[str, Any]:
        sim = self.get_sim()
        if not sim:
            return {}
        loc_mgr = self.read_q(sim + 0x558)
        loc = self.read_b(loc_mgr + 0x2c0) if loc_mgr else 0
        rel = self.read_b(loc_mgr + 0x2c1) if loc_mgr else 0
        act = self.read_b(loc_mgr + 0x2c2) if loc_mgr else 0

        tod_mgr = self.get_tod_mgr()
        tod = self.read_b(tod_mgr + 0x2d0) if tod_mgr else 0

        return {
            "location_id": loc,
            "location_name": LOC_NAMES.get(loc, f"Loc {loc}"),
            "nook_id": rel,
            "nook_name": NOOK_NAMES.get(rel, f"Spot {rel}"),
            "activity_id": act,
            "activity_name": ACT_NAMES.get(act, f"Act {act}"),
            "time_of_day_id": tod,
            "time_of_day_name": TOD_NAMES.get(tod, f"TOD {tod}"),
        }

    def check_spirit_match(self, s: SpiritInfo, room: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        if room is None:
            room = self.get_room_state()
        if not room:
            return False, "Not connected to game"
        missing = []
        if s.required_locs and 4 not in s.required_locs and room["location_id"] not in s.required_locs:
            expected = "/".join(LOC_NAMES.get(l, str(l)) for l in s.required_locs)
            missing.append(f"Move to Room: {expected} (current: {room['location_name']})")
        if s.required_rel_locs and room["nook_id"] not in s.required_rel_locs:
            expected = "/".join(NOOK_NAMES.get(n, str(n)) for n in s.required_rel_locs)
            missing.append(f"Move to Spot: {expected} (current: {room['nook_name']})")
        if s.required_tods and room["time_of_day_id"] not in s.required_tods:
            expected = "/".join(TOD_NAMES.get(t, str(t)) for t in s.required_tods)
            missing.append(f"Change Time of Day to {expected} (current: {room['time_of_day_name']})")
        if s.required_acts and room["activity_id"] not in s.required_acts:
            expected = "/".join(ACT_NAMES.get(a, str(a)) for a in s.required_acts)
            missing.append(f"Change Activity to {expected} (current: {room['activity_name']})")
        if s.required_sounds:
            missing.append("Turn on Soundscape audio (e.g. Birds/Rain/Fireplace)")

        if not missing:
            return True, "✅ All Room Conditions MATCH! Companion can be lured right now!"
        return False, "⚠️ Missing Conditions:\n• " + "\n• ".join(missing)

    def get_spirits(self) -> List[SpiritInfo]:
        sim = self.get_sim()
        if not sim:
            return []
        sim_cls = self._obj_cls(sim)

        def read_int_set(prop_name: str) -> set[int]:
            ptr, cnt, _ = self._read_tarray_hdr(sim + self.get_prop_offset(sim_cls, prop_name))
            if not ptr or not (0 < cnt < 500):
                return set()
            raw = self.rpm(ptr, cnt * 4)
            return set(struct.unpack(f"<{cnt}i", raw)) if raw and len(raw) == cnt * 4 else set()

        discovered = read_int_set("Spirit IDs discovered")
        luring = read_int_set("Spirit IDs luring")

        # Also merge with discovered IDs from save file if any
        sav_disc, sav_friend = self._read_spiritdex_file()
        for sid in sav_disc:
            discovered.add(sid)

        fp, fnum, _ = self._read_tarray_hdr(sim + self.get_prop_offset(sim_cls, "Spirit IDs to Friendship score"))
        friendships: Dict[int, Tuple[int, Optional[int]]] = {}
        if fp and 0 < fnum < 500:
            raw_map = self.rpm(fp, fnum * 16) or b""
            for i in range(len(raw_map) // 16):
                sid, val, _, _ = struct.unpack_from("<iiii", raw_map, i * 16)
                friendships[sid] = (val, fp + i * 16 + 4)

        # Merge with save file friendships
        for sid, score in sav_friend.items():
            if sid not in friendships:
                friendships[sid] = (score, None)

        ap, anum, _ = self._read_tarray_hdr(sim + self.get_prop_offset(sim_cls, "All Spirit Entries"))
        out: List[SpiritInfo] = []
        if ap and 0 < anum < 500:
            raw_entries = self.rpm(ap, anum * 496)
            if raw_entries and len(raw_entries) >= anum * 496:
                for i in range(anum):
                    entry_addr = ap + i * 496
                    str_ptr, str_len, _, sid, dn_idx = struct.unpack_from("<QIIiI", raw_entries, i * 496)
                    code = self._read_fstr_data(str_ptr, str_len)
                    dname = self.get_fname(dn_idx) or code
                    fval, faddr = friendships.get(sid, (None, None))

                    # Read conditions
                    cond_addr = entry_addr + 0xf8

                    def _tarray_u8(sub_off: int) -> List[int]:
                        p, n, _ = self._read_tarray_hdr(cond_addr + sub_off)
                        return list(self.rpm(p, n) or b"") if p and 0 < n < 64 else []

                    locs = _tarray_u8(0x08)
                    rel_locs = _tarray_u8(0x18)
                    tods = _tarray_u8(0x28)
                    acts = _tarray_u8(0x38)
                    sounds = _tarray_u8(0x48)
                    mins_raw = self.rpm(cond_addr + 0x88, 4)
                    mins = struct.unpack_from("<i", mins_raw, 0)[0] if mins_raw else 0

                    # Category
                    if sid in (901, 902) or (1 <= sid <= 25):
                        cat = "Bedroom"
                    elif 102 <= sid <= 113:
                        cat = "Kitchen"
                    elif 201 <= sid <= 211:
                        cat = "Train"
                    elif 301 <= sid <= 313:
                        cat = "Garden"
                    elif 401 <= sid <= 413:
                        cat = "Library"
                    else:
                        cat = "Bedroom"

                    tod_str = "/".join(TOD_NAMES.get(t, f"TOD {t}") for t in tods) if tods else "Any Time"
                    nook_str = "/".join(NOOK_NAMES.get(n, f"Spot {n}") for n in rel_locs) if rel_locs else "Any Spot"
                    act_str = "/".join(ACT_NAMES.get(a, f"Act {a}") for a in acts) if acts else "Any Activity"
                    snd_str = "Soundscape" if sounds else "Any Audio"
                    dur_str = f"{mins}m" if mins > 0 else "Instant"
                    clues = f"{cat} | {tod_str} | {nook_str} | {act_str} | {snd_str} ({dur_str})"

                    out.append(
                        SpiritInfo(
                            spirit_id=sid,
                            code_name=code,
                            display_name=dname,
                            discovered=sid in discovered,
                            luring=sid in luring,
                            friendship=fval,
                            friendship_elem_addr=faddr,
                            category=cat,
                            required_tods=tods,
                            required_locs=locs,
                            required_rel_locs=rel_locs,
                            required_acts=acts,
                            required_sounds=sounds,
                            minutes=mins,
                            clues_summary=clues,
                        )
                    )
        out.sort(key=lambda s: s.spirit_id)
        return out

    def max_all_friendships(self, score: int = 999) -> int:
        val = max(0, int(score))
        spirits = self.get_spirits()
        count = 0

        # 1. Update in-memory for all spirits with known element addresses
        for s in spirits:
            if s.friendship_elem_addr and self._write_fmt(s.friendship_elem_addr, "i", val):
                count += 1

        # 2. Update SCLS_Spiritdex.sav for all discovered spirits
        disc_ids, f_map = self._read_spiritdex_file()
        for s in spirits:
            if s.discovered:
                if s.spirit_id not in disc_ids:
                    disc_ids.append(s.spirit_id)
                f_map[s.spirit_id] = val
        self._save_spiritdex_file(disc_ids, f_map)

        # 3. Save to SCLS_Spiritdex.sav is already cleanly performed above
        return max(count, len(disc_ids))

    def set_spirit_friendship(self, spirit_id: int, score: int) -> bool:
        val = max(0, int(score))
        spirits = self.get_spirits()
        target = next((s for s in spirits if s.spirit_id == spirit_id), None)

        mem_ok = False
        if target and target.friendship_elem_addr:
            mem_ok = self._write_fmt(target.friendship_elem_addr, "i", val)

        disc_ids, f_map = self._read_spiritdex_file()
        if target and target.discovered and spirit_id not in disc_ids:
            disc_ids.append(spirit_id)
        f_map[spirit_id] = val
        sav_ok = self._save_spiritdex_file(disc_ids, f_map)

        return bool(mem_ok or sav_ok)

    def discover_spirit(self, spirit_id: int, friendship: int = 999) -> bool:
        val = max(0, int(friendship))
        disc_ids, f_map = self._read_spiritdex_file()
        if spirit_id not in disc_ids:
            disc_ids.append(spirit_id)
        f_map[spirit_id] = val
        sav_ok = self._save_spiritdex_file(disc_ids, f_map)

        if sim := self.get_sim():
            sim_cls = self._obj_cls(sim)
            d_ptr, d_num, d_max = self._read_tarray_hdr(sim + self.get_prop_offset(sim_cls, "Spirit IDs discovered"))
            if d_ptr and d_num < d_max:
                raw = self.rpm(d_ptr, d_num * 4) or b""
                curr_ids = list(struct.unpack(f"<{d_num}i", raw)) if len(raw) == d_num * 4 else []
                if spirit_id not in curr_ids:
                    self._write_fmt(d_ptr + d_num * 4, "i", spirit_id)
                    self._write_fmt(sim + self.get_prop_offset(sim_cls, "Spirit IDs discovered") + 8, "i", d_num + 1)
            try:
                self._call_named(sim, "Retroactively Unlock Spirit Achievements")
            except Exception:
                pass
        return bool(sav_ok)

    def discover_all_spirits(self, friendship: int = 999) -> int:
        val = max(0, int(friendship))
        spirits = self.get_spirits()
        all_ids = (
            [s.spirit_id for s in spirits]
            if spirits
            else list(range(1, 26)) + [901, 902] + list(range(102, 114)) + list(range(201, 212)) + list(range(301, 314)) + list(range(401, 414))
        )
        f_map = {sid: val for sid in all_ids}
        self._save_spiritdex_file(all_ids, f_map)

        for s in spirits:
            if s.friendship_elem_addr:
                self._write_fmt(s.friendship_elem_addr, "i", val)

        if sim := self.get_sim():
            try:
                self._call_named(sim, "Retroactively Unlock Spirit Achievements")
            except Exception:
                pass
        return len(all_ids)

    # --- Content Packages, Steam Achievements, Dev Menus ---
    def unlock_all_content_packages(self) -> List[int]:
        gi = self.get_game_instance()
        if not gi:
            return []
        off = self.get_prop_offset(self._obj_cls(gi), "Owned Content Packages")
        ptr, num, mx = self._read_tarray_hdr(gi + off)
        if not ptr or mx == 0:
            return []
        target = list(self.rpm(ptr, num) or b"") if num > 0 else []
        for pkg_id in range(0, 13):
            if pkg_id not in target and len(target) < mx:
                target.append(pkg_id)
        self.wpm(ptr, bytes(target))
        self._write_fmt(gi + off + 8, "I", len(target))
        return target

    def sync_steam_achievements(self) -> None:
        if pc := self.get_pc():
            self._call_named(pc, "Retroactively assign Steam Achievements for Lvl")
        if sim := self.get_sim():
            self._call_named(sim, "Retroactively Unlock Spirit Achievements")

    def toggle_dev_menu(self, which: str, visible: bool) -> None:
        hud = self.get_hud()
        if not hud or not self._fn_set_visibility:
            return
        prop_name = "WBP_CheatMenu" if which == "cheat" else "WBP_DebugMenu"
        widget = self.read_q(hud + self.get_prop_offset(self._obj_cls(hud), prop_name))
        if widget:
            # ESlateVisibility: 0=Visible, 2=Collapsed
            self.call_ufunction(widget, self._fn_set_visibility, struct.pack("<B", 0 if visible else 2))

    # --- Full Live Snapshot ---
    def get_snapshot(self) -> GameSnapshot:
        if not self.is_alive():
            return GameSnapshot(attached=False)

        pc = self.get_pc()
        if not pc:
            return GameSnapshot(attached=True, pid=self.pid, hook_installed=self.hook_installed)

        xp, lvl, credits, d_login, d_todo, d_pomo, parallax = self._read_props(
            pc,
            (
                ("Total Cumulative XP", "i"),
                ("Current LVL", "i"),
                ("Current Spirit Credits", "i"),
                ("canEarnDailyEXP_Login", "?"),
                ("canEarnDailyEXP_Todo", "?"),
                ("canEarnDailyEXP_Pomo", "?"),
                ("Parallax Effect Strength", "d"),
            ),
        )
        norm, left, thresh = self._calc_level_progress(xp, lvl)

        td = 1.0
        if ws := self.get_world_settings():
            td = self.read_f(ws + self.get_prop_offset(self._obj_cls(ws), "TimeDilation"))

        playtime, t_spd, t_shk = 0, 0.0, 1.0
        if prod := self.get_prod_mgr():
            playtime, t_spd, t_shk = self._read_props(
                prod, (("PlaytimeToday", "i"), ("TrainSpeed", "d"), ("TrainShakeMultiplier", "d"))
            )

        tod_val, sync_clk = 0, True
        if tod := self.get_tod_mgr():
            tod_val, sync_clk = self._read_props(
                tod, (("CurrentTimeOfDay", "B"), ("Play with real life clock (or play with set lighting)", "?"))
            )

        muted = ui_hidden = False
        if hud := self.get_hud():
            muted, ui_hidden = self._read_props(hud, (("isMuted", "?"), ("isUIHidden", "?")))

        is_luring = False
        disc_cnt = tot_spirits = 0
        if sim := self.get_sim():
            sim_cls = self._obj_cls(sim)
            is_luring = bool(self.read_b(sim + self.get_prop_offset(sim_cls, "isLuring")))
            disc_cnt = self.read_i(sim + self.get_prop_offset(sim_cls, "Spirit IDs discovered") + 8)
            tot_spirits = self.read_i(sim + self.get_prop_offset(sim_cls, "All Spirit Entries") + 8)

        _, p_v2, p_tmr, p_sw = self._get_pomodoro_widgets()
        p_st = p_loops = p_seg = t_st = sw_st = sw_sec = 0
        t_pass = t_len = 0.0
        if p_v2:
            p_st, p_loops, p_seg = self._read_props(p_v2, (("State", "B"), ("Loops", "i"), ("CurrentSegment", "i")))
        if p_tmr:
            t_st, t_pass, t_len = self._read_props(p_tmr, (("State", "B"), ("TimePassed", "d"), ("TimerLength", "d")))
        if p_sw:
            sw_st, sw_sec = self._read_props(p_sw, (("State", "B"), ("TimePassed", "i")))

        pkgs: List[int] = []
        if gi := self.get_game_instance():
            off = self.get_prop_offset(self._obj_cls(gi), "Owned Content Packages")
            pp, pn, _ = self._read_tarray_hdr(gi + off)
            if pp and 0 < pn <= 32:
                pkgs = list(self.rpm(pp, pn) or b"")

        xp_calls = raw_xp = mult_xp = 0
        if self.cave_addr:
            raw_tel = self.rpm(self.cave_addr + self.OFF_TOTAL_XP_CALLS, 16)
            if raw_tel and len(raw_tel) == 16:
                xp_calls, raw_xp, mult_xp = struct.unpack("<Qii", raw_tel)

        return GameSnapshot(
            attached=True,
            pid=self.pid,
            hook_installed=self.hook_installed,
            xp=xp,
            level=lvl,
            credits=credits,
            xp_progress_norm=norm,
            xp_left_next=left,
            xp_next_threshold=thresh,
            daily_login_avail=d_login,
            daily_todo_avail=d_todo,
            daily_pomo_avail=d_pomo,
            time_dilation=td,
            playtime_today_sec=playtime,
            train_speed=t_spd,
            train_shake=t_shk,
            time_of_day=tod_val,
            sync_real_clock=sync_clk,
            parallax_strength=parallax,
            is_muted=muted,
            is_ui_hidden=ui_hidden,
            is_luring=is_luring,
            discovered_count=disc_cnt,
            total_spirits=tot_spirits,
            pomo_state=p_st,
            pomo_loops=p_loops,
            pomo_segment=p_seg,
            timer_state=t_st,
            timer_passed=t_pass,
            timer_length=t_len,
            stopwatch_state=sw_st,
            stopwatch_passed=sw_sec,
            owned_packages=pkgs,
            xp_calls=xp_calls,
            last_raw_xp=raw_xp,
            last_mult_xp=mult_xp,
        )
