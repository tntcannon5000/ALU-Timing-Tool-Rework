"""
Data Extractor — Direct Process Memory Reader (pymem-based)

Architecture (v2 — freeze-capture design):
═══════════════════════════════════════════

Visual Timer hook  (PERMANENT — ESI cannot be read from memory):
  • Installed once at startup; remains active for the session.
  • Provides the race-state indicator every poll cycle.
  • Removed cleanly on stop().

Hooks 1-4  (TEMPORARY — freeze-fire-remove cycle):
  • AOB scan + stub allocation happen while game runs normally (read-only).
  • Game is FROZEN via SuspendThread on all game threads.
  • JMP patches are written to the frozen, non-executing code.
  • Game is UNFROZEN for just long enough for the hooks to fire once
    (~1–500 ms depending on which code paths are active).
  • Game is FROZEN again.
  • rdi and r13 base pointers are read from stub data areas.
  • Original bytes are restored (hooks removed).
  • Stub pages are freed.
  • Game is UNFROZEN permanently.
  • From this point onward, ALL telemetry is read by directly offsetting
    the captured rdi/r13 base pointers — ZERO hooks active.

Anti-cheat window: only the brief unfreeze period (≤ 500 ms) while the
temporary JMP patches exist.  The game sends no data to the network while
frozen, so the anti-cheat engine cannot observe the patches.

Re-capture: triggered whenever the Visual Timer transitions from "menus"
back to "racing" (new race ⟹ game may allocate a new race-manager object
at a different address).

Public API is identical to CheatEngineClient so timer_v5_CE.py works
with zero logic changes (only the import/instantiation line changes).

Hook sites (mirrors ALU_Trainer_v2.4.CT exactly):
  Hook 1 — Dashboard  : movss [rdi+0x1B8],xmm1   (8 bytes)  → RPM + Gear
  Hook 2 — Timer      : mov rdx,[rdi+0xF8]         (7 bytes)  → race µs timer
  Hook 3 — Progress   : mov [rdi+0x1D8],eax        (6 bytes)  → progress float
  Hook 4 — VisualTimer: base+0x5CC82F (static)     (9 bytes)  → race-state (PERMANENT)

After capture, direct-read offsets used:
  rdi_base + 0x10    → RaceTimer     (uint32 µs)
  rdi_base + 0x1D8   → RaceProgress  (float 0.0–1.0)
  rdi_base + 0x1B8   → RaceRPM       (float → truncate to int)
  rdi_base + 0xA0    → RaceGear      (uint32)
"""

import ctypes
import ctypes.wintypes as wintypes
import math
import re
import struct
import threading
import time
from typing import Optional, Tuple, Union

import pymem
import pymem.process
import pymem.pattern

# ---------------------------------------------------------------------------
# Windows API wrappers
# ---------------------------------------------------------------------------

_k32 = ctypes.windll.kernel32

MEM_COMMIT             = 0x1000
MEM_RESERVE            = 0x2000
MEM_RELEASE            = 0x8000
PAGE_EXECUTE_READWRITE = 0x40

TH32CS_SNAPTHREAD     = 0x00000004
THREAD_SUSPEND_RESUME = 0x00000002


class _THREADENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize",             wintypes.DWORD),
        ("cntUsage",           wintypes.DWORD),
        ("th32ThreadID",       wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri",          ctypes.c_long),
        ("tpDeltaPri",         ctypes.c_long),
        ("dwFlags",            wintypes.DWORD),
    ]


def _freeze_threads(pid: int) -> list:
    """
    Suspend every thread belonging to *pid*.

    Returns a list of open HANDLE values.  Pass the same list to
    _unfreeze_threads() to resume and close them.

    Uses CreateToolhelp32Snapshot + Thread32First/Next to enumerate
    system threads, then OpenThread + SuspendThread per match.
    """
    snap = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    if snap == wintypes.HANDLE(-1).value:
        raise OSError(f"CreateToolhelp32Snapshot failed: error {ctypes.GetLastError()}")

    te = _THREADENTRY32()
    te.dwSize = ctypes.sizeof(_THREADENTRY32)

    handles = []
    try:
        if _k32.Thread32First(snap, ctypes.byref(te)):
            while True:
                if te.th32OwnerProcessID == pid:
                    h = _k32.OpenThread(THREAD_SUSPEND_RESUME, False, te.th32ThreadID)
                    if h:
                        _k32.SuspendThread(h)
                        handles.append(h)
                if not _k32.Thread32Next(snap, ctypes.byref(te)):
                    break
    finally:
        _k32.CloseHandle(snap)

    return handles


def _unfreeze_threads(handles: list) -> None:
    """Resume and close all thread handles from _freeze_threads()."""
    for h in handles:
        _k32.ResumeThread(h)
        _k32.CloseHandle(h)


def _valloc_near(handle: int, near: int, size: int = 0x1000) -> int:
    """
    Allocate PAGE_EXECUTE_READWRITE memory within ±2 GB of *near*.

    Windows requires the allocation to be within 32-bit relative range of
    the hook site so that the 5-byte E9 relative JMP can reach it — the
    same constraint CE satisfies with  alloc(newmem,$1000,INJECT_POINT).

    Scans outward in 64 KB steps (minimum Windows allocation granularity).
    Raises MemoryError if no suitable region is found.
    """
    fn = _k32.VirtualAllocEx
    fn.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_size_t,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    fn.restype = ctypes.c_void_p  # returns int or None

    flags = MEM_COMMIT | MEM_RESERVE
    prot  = PAGE_EXECUTE_READWRITE
    step  = 0x10000  # 64 KB — Windows allocation granularity

    for delta in range(0, 0x78000000, step):          # scan up to ~1.875 GB
        for sign in (1, -1):
            if delta == 0 and sign == -1:
                continue
            candidate = near + sign * delta
            if not (0x10000 <= candidate <= 0x7FFFFFFFFFFF):
                continue
            result = fn(handle, ctypes.c_void_p(candidate), size, flags, prot)
            if result:
                return result

    raise MemoryError(f"Cannot allocate near {near:#x} within ±2 GB")


def _vfree(handle: int, address: int) -> None:
    fn = _k32.VirtualFreeEx
    fn.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                   ctypes.c_size_t, wintypes.DWORD]
    fn.restype  = wintypes.BOOL
    fn(handle, ctypes.c_void_p(address), 0, MEM_RELEASE)


def _vprotect(handle: int, address: int, size: int, new_prot: int) -> int:
    """Change memory protection; returns old protection value."""
    old = wintypes.DWORD(0)
    fn  = _k32.VirtualProtectEx
    fn.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
                   wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    fn.restype  = wintypes.BOOL
    ok = fn(handle, ctypes.c_void_p(address), size, new_prot, ctypes.byref(old))
    if not ok:
        raise OSError(
            f"VirtualProtectEx failed at {address:#x}: "
            f"error {ctypes.GetLastError()}"
        )
    return old.value


# ---------------------------------------------------------------------------
# x86-64 encoding helpers
# ---------------------------------------------------------------------------

def _rel32(from_next_ip: int, to: int) -> bytes:
    """
    4-byte little-endian relative displacement for a 5-byte E9 JMP or a
    RIP-relative MOV/etc.

    from_next_ip: address of the instruction that FOLLOWS the rel32 field,
                  i.e. the RIP value at execution time.
    to:           target absolute address.
    """
    delta = to - from_next_ip
    if not (-0x80000000 <= delta <= 0x7FFFFFFF):
        raise OverflowError(
            f"32-bit relative displacement overflows: "
            f"{from_next_ip:#x} → {to:#x}  (delta={delta:+d})"
        )
    return struct.pack("<i", delta)


def _jmp_rel32(from_ip: int, to: int) -> bytes:
    """5-byte E9 relative JMP.  from_ip is the address of the JMP opcode."""
    return b"\xE9" + _rel32(from_ip + 5, to)


def _jmp_abs(to: int) -> bytes:
    """14-byte absolute indirect JMP: FF 25 00000000 <8-byte-addr>."""
    return b"\xFF\x25\x00\x00\x00\x00" + struct.pack("<Q", to)


def _jmp_back(stub_pos: int, target: int) -> bytes:
    """
    Emit either a 5-byte relative or 14-byte absolute JMP back to target,
    depending on whether target falls within 32-bit rel range.
    """
    try:
        return _jmp_rel32(stub_pos, target)
    except OverflowError:
        return _jmp_abs(target)


# ---------------------------------------------------------------------------
# Stub builders
# ---------------------------------------------------------------------------
#
# Memory layout for EVERY allocated stub page (4 KB):
#
#   alloc_base + 0  … _CODE_OFFSET-1  : data labels (telemetry storage)
#   alloc_base + _CODE_OFFSET …       : executable trampoline code
#
# Each builder returns the full page as bytes.

_CODE_OFFSET = 64   # data area occupies the first 64 bytes


def _build_dashboard_stub(alloc_base: int, return_addr: int) -> bytes:
    """
    Hook: movss [rdi+0x1B8],xmm1   (F3 0F 11 8F B8 01 00 00 — 8 bytes)

    Data layout at alloc_base:
      +0  : RaceRPM_Raw (float,   4 bytes) — unused post-capture
      +4  : RaceRPM_Int (uint32,  4 bytes) — unused post-capture
      +8  : RaceGear    (uint32,  4 bytes) — unused post-capture
      +12 : rdi_base    (qword,   8 bytes) — race-manager struct base address
            PRIMARY rdi capture source; fires every frame during active racing.

    Patch at hook site: E9 <rel32> 90 90 90  (5-byte JMP + 3 NOPs)
    """
    code_base = alloc_base + _CODE_OFFSET
    code = bytearray()

    def pos() -> int:
        return code_base + len(code)

    # ── original instruction ──────────────────────────────────────────────
    # movss [rdi+0x1B8],xmm1                               F3 0F 11 8F B8 01 00 00
    code += b"\xF3\x0F\x11\x8F\xB8\x01\x00\x00"

    # ── copy RPM float → RaceRPM_Raw ─────────────────────────────────────
    # movss [rip+XX],xmm1                                  F3 0F 11 0D <rel32>
    # Instruction length = 8; RIP after = pos()+8
    code += b"\xF3\x0F\x11\x0D"
    code += _rel32(pos() + 4, alloc_base + 0)

    # ── convert & copy RPM int → RaceRPM_Int ─────────────────────────────
    # push rax                                             50
    code += b"\x50"
    # cvttss2si eax,xmm1                                  F3 0F 2C C1
    code += b"\xF3\x0F\x2C\xC1"
    # mov [rip+XX],eax  — RaceRPM_Int                     89 05 <rel32>
    code += b"\x89\x05"
    code += _rel32(pos() + 4, alloc_base + 4)
    # pop rax                                              58
    code += b"\x58"

    # ── copy Gear → RaceGear ─────────────────────────────────────────────
    # push rax                                             50
    code += b"\x50"
    # mov eax,[rdi+0xA0]                                  8B 87 A0 00 00 00
    code += b"\x8B\x87\xA0\x00\x00\x00"
    # mov [rip+XX],eax  — RaceGear                        89 05 <rel32>
    code += b"\x89\x05"
    code += _rel32(pos() + 4, alloc_base + 8)
    # pop rax                                              58
    code += b"\x58"

    # ── capture rdi struct base → rdi_base (+12) ────────────────────────
    # This fires every frame during racing whenever the dashboard/RPM updates,
    # making it the primary and most reliable source for rdi_base capture.
    # mov [rip+XX],rdi                                    48 89 3D <rel32>
    code += b"\x48\x89\x3D"
    code += _rel32(pos() + 4, alloc_base + 12)

    # ── JMP back ─────────────────────────────────────────────────────────
    code += _jmp_back(pos(), return_addr)

    return bytes(bytearray(_CODE_OFFSET) + code)


def _build_timer_stub(alloc_base: int, return_addr: int) -> bytes:
    """
    Hook: mov rdx,[rdi+0xF8]   (48 8B 97 F8 00 00 00 — 7 bytes)
    This is INJECT_TIMER+4 (the instruction immediately after
    ``add [rdi+10],rax``).

    Data layout at alloc_base:
      +0 : RaceTimer (uint32,  4 bytes — µs snapshot, kept for reference)
      +4 : padding   (4 bytes)
      +8 : rdi_base  (qword,   8 bytes) — race-manager struct base address

    rdi_base is the KEY OUTPUT of the freeze-capture cycle.  After the
    temporary hooks have fired once and been removed, all timer/progress/
    RPM/gear values are read directly from rdi_base + known offsets with
    ZERO hooks active.

    Patch at hook site: E9 <rel32> 90 90  (5-byte JMP + 2 NOPs)
    """
    code_base = alloc_base + _CODE_OFFSET
    code = bytearray()

    def pos() -> int:
        return code_base + len(code)

    # ── copy timer µs → RaceTimer (+0) ───────────────────────────────────
    # push rbx                                             53
    code += b"\x53"
    # mov ebx,[rdi+0x10]                                  8B 5F 10
    code += b"\x8B\x5F\x10"
    # mov [rip+XX],ebx  — RaceTimer                       89 1D <rel32>
    code += b"\x89\x1D"
    code += _rel32(pos() + 4, alloc_base + 0)
    # pop rbx                                              5B
    code += b"\x5B"

    # ── capture rdi struct base → rdi_base (+8) ──────────────────────────
    # mov [rip+XX],rdi
    # Encoding: REX.W(48) + MOV r/m64,r64(89) + ModRM(mod=00,reg=rdi(7),rm=RIP(5)=3D)
    # Instruction is 7 bytes: 48 89 3D <rel32>
    code += b"\x48\x89\x3D"
    code += _rel32(pos() + 4, alloc_base + 8)

    # ── original instruction ──────────────────────────────────────────────
    # mov rdx,[rdi+0xF8]                                  48 8B 97 F8 00 00 00
    code += b"\x48\x8B\x97\xF8\x00\x00\x00"

    # ── JMP back ─────────────────────────────────────────────────────────
    code += _jmp_back(pos(), return_addr)

    return bytes(bytearray(_CODE_OFFSET) + code)


def _build_progress_stub(alloc_base: int, return_addr: int) -> bytes:
    """
    Hook: mov [rdi+0x1D8],eax   (89 87 D8 01 00 00 — 6 bytes)

    This instruction is player-specific — it only executes for the player's race
    manager struct, never for AI cars.  This makes it the most reliable source
    for rdi_base capture.

    Data layout at alloc_base:
      +0 : RaceProgress (float stored as 4-byte IEEE 754 integer — reinterpret
           as float when reading; this matches the CT's readFloat() call)
      +4 : rdi_base (qword, 8 bytes) — player race-manager struct base address
           PRIMARY rdi capture source (player-only code path).

    Patch at hook site: E9 <rel32> 90  (5-byte JMP + 1 NOP)
    """
    code_base = alloc_base + _CODE_OFFSET
    code = bytearray()

    def pos() -> int:
        return code_base + len(code)

    # ── original instruction ──────────────────────────────────────────────
    # mov [rdi+0x1D8],eax                                 89 87 D8 01 00 00
    code += b"\x89\x87\xD8\x01\x00\x00"

    # ── copy progress float bits → RaceProgress ──────────────────────────
    # push rbx                                             53
    code += b"\x53"
    # mov ebx,[rdi+0x1D8]  (read back the value just written)  8B 9F D8 01 00 00
    code += b"\x8B\x9F\xD8\x01\x00\x00"
    # mov [rip+XX],ebx  — RaceProgress                    89 1D <rel32>
    code += b"\x89\x1D"
    code += _rel32(pos() + 4, alloc_base + 0)
    # pop rbx                                              5B
    code += b"\x5B"

    # ── capture rdi_base (+4) ─────────────────────────────────────────────
    # This fires only for the player's race struct — not AI cars — making it
    # the most reliable rdi capture source.
    # mov [rip+XX],rdi                                    48 89 3D <rel32>
    code += b"\x48\x89\x3D"
    code += _rel32(pos() + 4, alloc_base + 4)

    # ── JMP back ─────────────────────────────────────────────────────────
    code += _jmp_back(pos(), return_addr)

    return bytes(bytearray(_CODE_OFFSET) + code)



def _build_vt_stub(alloc_base: int, return_addr: int) -> bytes:
    """
    Hook: xor rax,rsi; mov r14d,0x10
          (48 33 C6 41 BE 10 00 00 00 — 9 bytes, static offset base+0x5CC82F)

    ESI holds the raw visual-timer / race-state value BEFORE the XOR.
    We copy ESI → VisualTimer before executing both original instructions.

    This is the PERMANENT hook.  Visual Timer is sourced from a register
    (ESI) and cannot be read directly from a known memory address, so
    the trampoline must remain active for the session.

    Data layout at alloc_base:
      +0 : VisualTimer (uint32, 4 bytes)

    Patch at hook site: E9 <rel32> 90 90 90 90  (5-byte JMP + 4 NOPs)
    """
    code_base = alloc_base + _CODE_OFFSET
    code = bytearray()

    def pos() -> int:
        return code_base + len(code)

    # ── copy ESI → VisualTimer ───────────────────────────────────────────
    # push rax                                             50
    code += b"\x50"
    # mov eax,esi                                         89 F0
    code += b"\x89\xF0"
    # mov [rip+XX],eax  — VisualTimer                     89 05 <rel32>
    code += b"\x89\x05"
    code += _rel32(pos() + 4, alloc_base + 0)
    # pop rax                                              58
    code += b"\x58"

    # ── original instructions ─────────────────────────────────────────────
    # xor rax,rsi                                         48 33 C6
    code += b"\x48\x33\xC6"
    # mov r14d,0x10                                       41 BE 10 00 00 00
    code += b"\x41\xBE\x10\x00\x00\x00"

    # ── JMP back ─────────────────────────────────────────────────────────
    code += _jmp_back(pos(), return_addr)

    return bytes(bytearray(_CODE_OFFSET) + code)


def _build_local_player_stub(alloc_base: int, return_addr: int) -> bytes:
    """
    Hook: mov [rbx+08],rax       (48 89 43 08 — 4 bytes)
          movss xmm1,[r14+130h] (F3 41 0F 10 8E 30 01 00 00 — 9 bytes)
    Total hooksite: 13 bytes → patch with JMP(5) + NOP×8

    Data layout at alloc_base:
      +0 : local_player_ptr_struct_val (qword, 8 bytes) — captured rax
           Player base = [rax + local_struct_offset]
           Velocity X/Y/Z at player_base + 0x160 / 0x164 / 0x168
    """
    code_base = alloc_base + _CODE_OFFSET
    code = bytearray()

    def pos() -> int:
        return code_base + len(code)

    # ── original instruction 1: mov [rbx+08],rax ─────────────────────────
    code += b"\x48\x89\x43\x08"

    # ── capture rax → local_player_ptr_struct_val (+0) ───────────────────
    # mov [rip+XX],rax                                   48 89 05 <rel32>
    code += b"\x48\x89\x05"
    code += _rel32(pos() + 4, alloc_base + 0)

    # ── original instruction 2: movss xmm1,[r14+0x130] ───────────────────
    code += b"\xF3\x41\x0F\x10\x8E\x30\x01\x00\x00"

    # ── JMP back ─────────────────────────────────────────────────────────
    code += _jmp_back(pos(), return_addr)

    return bytes(bytearray(_CODE_OFFSET) + code)


def _build_steering_stub(alloc_base: int, return_addr: int) -> bytes:
    """
    Hook: movss [rsi+0x1540],xmm1   (F3 0F 11 8E 40 15 00 00 — 8 bytes)

    This instruction writes the current steering wheel angle in radians.
    The steering *input* value (−1.0 to +1.0) is stored at rsi+0x1544,
    exactly 4 bytes after the hooked write target.

    Data layout at alloc_base:
      +0 : SteeringInput (float, 4 bytes) — raw IEEE-754 bits of steering input.

    Patch at hook site: E9 <rel32> 90 90 90  (5-byte JMP + 3 NOPs)
    """
    code_base = alloc_base + _CODE_OFFSET
    code = bytearray()

    def pos() -> int:
        return code_base + len(code)

    # ── original instruction: movss [rsi+0x1540],xmm1 ────────────────────
    # F3 0F 11 8E 40 15 00 00
    code += b"\xF3\x0F\x11\x8E\x40\x15\x00\x00"

    # ── copy steering input float bits from [rsi+0x1544] ─────────────────
    # push rax                                             50
    code += b"\x50"
    # mov eax,[rsi+0x1544]                                 8B 86 44 15 00 00
    code += b"\x8B\x86\x44\x15\x00\x00"
    # mov [rip+XX],eax  — SteeringInput                    89 05 <rel32>
    code += b"\x89\x05"
    code += _rel32(pos() + 4, alloc_base + 0)
    # pop rax                                              58
    code += b"\x58"

    # ── JMP back ─────────────────────────────────────────────────────────
    code += _jmp_back(pos(), return_addr)

    return bytes(bytearray(_CODE_OFFSET) + code)


# ---------------------------------------------------------------------------
# DataExtractor — drop-in replacement for CheatEngineClient
# ---------------------------------------------------------------------------

class DataExtractor:
    """
    Drop-in replacement for CheatEngineClient.

    Reads the same telemetry values as the v2.4 CT by installing identical
    trampoline hooks directly via pymem / Windows API.

    Public interface is intentionally identical to CheatEngineClient:
    start(), stop(), get_values(), get_all_values(), get_timer_ms(),
    get_progress_percent(), get_visual_timer(), get_rpm(), get_gear(),
    is_connected(), get_stats(),
    reads_ok, reads_failed.
    """

    # ── AOB patterns (bytes wrapped in re.escape so pymem treats them
    #    as literal byte sequences, not regex patterns) ──────────────────

    # Hook 1 — Dashboard: movss [rdi+0x1B8],xmm1
    _AOB_DASHBOARD = re.escape(b"\xF3\x0F\x11\x8F\xB8\x01\x00\x00")

    # Hook 2 — Timer context: add [rdi+10],rax + *mov rdx,[rdi+0xF8]* + mov rax,[rdx+8]
    # We scan all 15 bytes for uniqueness, then hook at byte +4.
    _AOB_TIMER_CTX = re.escape(
        b"\x48\x01\x47\x10"               # add [rdi+10],rax   (skip)
        b"\x48\x8B\x97\xF8\x00\x00\x00"   # mov rdx,[rdi+0xF8] ← hook here (+4)
        b"\x48\x8B\x42\x08"               # mov rax,[rdx+8]
    )
    _AOB_TIMER_HOOK_OFFSET = 4

    # Hook 3 — Progress: mov [rdi+0x1D8],eax ; add rsp,0x38
    _AOB_PROGRESS = re.escape(b"\x89\x87\xD8\x01\x00\x00\x48\x83\xC4\x38")

    # Hook 4 — Visual Timer (permanent; static offset primary, AOB fallback)
    _VT_STATIC_OFFSET = 0x5CC82F
    _VT_EXPECTED      = b"\x48\x33\xC6\x41\xBE\x10\x00\x00\x00"
    _AOB_VT           = re.escape(_VT_EXPECTED)

    # Hook 5 — Local Player Ptr: mov [rbx+08],rax + movss xmm1,[r14+130h] (13 bytes)
    # Captures rax = localPlayerPtrStruct value used to derive player_base.
    _AOB_LOCAL_PLAYER_PTR = re.escape(
        b"\x48\x89\x43\x08"                    # mov [rbx+08],rax   (4)
        b"\xF3\x41\x0F\x10\x8E\x30\x01\x00\x00"  # movss xmm1,[r14+130h] (9)
    )  # total 13 bytes — patch with JMP(5) + NOP×8

    # For reading the struct offset embedded in: mov rax,[rcx+NNNNNNNN]
    # Scan for the fixed bytes that follow it to locate the displacement.
    _AOB_LOCAL_STRUCT_OFFSET_CTX = re.escape(
        b"\x83\xB8\x04\x01\x00\x00\x02\x0F\x95\xC0"
    )  # cmp dword ptr [rax+104h],2 ; setne al

    # Hook 6 — Steering (permanent): movss [rsi+0x1540],xmm1
    # Read input value at rsi+0x1544 — 8-byte instruction → JMP(5) + NOP×3
    _AOB_STEERING = re.escape(
        b"\xF3\x0F\x11\x8E\x40\x15\x00\x00\x48\x63\x48"
    )  # movss [rsi+0x1540],xmm1 + first 3 bytes of next instruction

    PROCESS_NAME = "Asphalt9_Steam_x64_rtl.exe"

    # Safety hard cap for the capture poll loop (seconds).  The loop normally exits
    # as soon as VT leaves 0 (race started → hooks fire, or user quit → VT=1M).
    # This value is only reached if something goes catastrophically wrong.
    _CAPTURE_SAFETY_TIMEOUT_S: float = 300.0

    # Developer flag: set False to skip SuspendThread/ResumeThread during the
    # address-capture cycle.  Without freezing, JMP patches are live while the
    # game runs — safe enough for quick testing on a temp account, but higher
    # anti-cheat exposure.  True = safer default.
    FREEZE_FOR_CAPTURE: bool = True

    def __init__(self, poll_interval: float = 0.001):
        self.poll_interval = poll_interval

        # pymem state
        self._pm:     Optional[pymem.Pymem] = None
        self._base:   int                   = 0
        self._module                        = None

        # ── Permanent VT hook ────────────────────────────────────────────
        self._alloc_vt:     Optional[int] = None   # stub page for VT
        self._inj_vt:       Optional[int] = None   # patched address
        self._saved_vt:     dict          = {}      # {addr: orig_bytes}
        self._vt_installed: bool          = False

        # ── Permanent Steering hook ───────────────────────────────────────
        self._alloc_steering:     Optional[int] = None
        self._inj_steering:       Optional[int] = None
        self._saved_steering:     dict          = {}
        self._steering_installed: bool          = False

        # ── Captured struct base addresses (set after _capture_addresses) ──
        # Each hook uses a DIFFERENT rdi pointing to a different game object:
        #   _rdi_progress  : progress struct  → progress @ +0x1D8
        #   _rdi_dash      : car-physics struct → rpm @ +0x1B8, gear @ +0xA0
        #   _rdi_timer     : timer struct       → race timer @ +0x10
        self._rdi_progress: Optional[int] = None
        self._rdi_dash:     Optional[int] = None
        self._rdi_timer:    Optional[int] = None
        self._direct_mode:  bool          = False

        # ── AOB/stub cache + pre-scan state ─────────────────────────────
        # AOB addresses are stable across game sessions; cache after first scan.
        self._cached_injs:    dict           = {}   # {1: inj1, 2: inj2, 3: inj3}
        # Pre-scan: Steps 1+2 are run during the countdown so race-start
        # capture only needs Steps 3-8 (≈5 ms freeze + ≤500 ms poll).
        self._prescan_allocs: dict           = {}   # {1: alloc1, 2: alloc2, 3: alloc3}
        self._prescan_ready:  bool           = False
        self._prescan_lock:   threading.Lock = threading.Lock()
        # Deferred progress capture (launched when fast exit triggers)
        self._deferred_prog_alloc: Optional[int]   = None
        self._deferred_prog_inj:   Optional[int]   = None
        self._deferred_prog_orig:  Optional[bytes] = None

        # ── Emergency cleanup: live temporary hooks ───────────────────────
        # Populated in Step 3 of _capture_addresses(), cleared in Steps 6+8.
        # Used by _emergency_remove_temp_hooks() to restore dangling JMP patches
        # if the program exits mid-capture or while deferred progress is pending.
        self._live_temp_patches: dict = {}   # {inj_addr: orig_bytes}
        self._live_temp_allocs:  list = []   # stub page addresses not yet freed

        # ── Change-detection state (for synchronous read()) ──────────────
        self._prev_vt:           int            = -1    # last VT seen by read()
        self._prev_vals: Optional[dict]         = None  # last returned value dict
        self._first_read_logged: bool           = False
        self._last_vt_log:       float          = 0.0   # timestamp for periodic VT log

        # ── Local player pointer (for velocity) ────────────────────────────
        # Captured via Hook 5 during _capture_addresses().
        # _local_player_ptr_val = captured rax at the hook site
        # _local_struct_offset  = displacement from the struct-offset instruction
        # player_base each frame = [_local_player_ptr_val + _local_struct_offset]
        # Velocity X/Y/Z at player_base + 0x160 / 0x164 / 0x168
        self._local_player_ptr_val: Optional[int] = None
        self._local_struct_offset:  int           = 0   # set by _read_local_struct_offset

        # ── Latest telemetry (protected by _lock) ────────────────────────
        self._lock           = threading.Lock()
        self._timer_raw:     int   = 0
        self._progress_raw:  float = 0.0
        self._rpm:           int   = 1250
        self._gear:          int   = 0
        self._visual_timer:  int   = 1000000
        self._velocity_raw:  float = 0.0
        self._steering_raw:  float = 0.0
        self._connected:     bool  = False
        self._last_ok:       float = 0.0

        # ── Public counters (matching CheatEngineClient) ───────────────────
        self.reads_ok:          int = 0
        self.reads_failed:      int = 0
        self._last_fail_reason: str = ""

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def start(self) -> None:
        """
        Attempt to attach to the game process and install the permanent VT hook.
        Non-blocking — if the game is not running yet, read() will retry
        attach and hook installation on each call automatically.
        """
        print(f"[DataExtractor] Starting — targeting {self.PROCESS_NAME}")
        if self._pm is None:
            self._attach()
        if self._pm is not None and not self._vt_installed:
            self._install_vt_hook()
        if self._pm is not None and not self._steering_installed:
            self._install_steering_hook()
        if self._pm is not None and self._local_struct_offset == 0:
            self._read_local_struct_offset()

    def stop(self) -> None:
        """Remove all hooks (permanent VT + steering + any live temporary hooks) and release resources."""
        self._emergency_remove_temp_hooks()
        self._remove_steering_hook()
        self._remove_vt_hook()
        print("[DataExtractor] Stopped")

    # -----------------------------------------------------------------------
    # Public accessors — identical to CheatEngineClient
    # -----------------------------------------------------------------------

    def get_values(self) -> Tuple[int, float]:
        with self._lock:
            return self._timer_raw, self._progress_raw

    def get_all_values(self) -> dict:
        with self._lock:
            return {
                "timer_raw":    self._timer_raw,
                "progress":     self._progress_raw,
                "rpm":          self._rpm,
                "gear":         self._gear,
                "visual_timer": self._visual_timer,
                "velocity_raw": self._velocity_raw,
                "steering_raw": self._steering_raw,
            }

    def get_timer_ms(self) -> int:
        with self._lock:
            return self._timer_raw // 1000

    def get_progress_percent(self) -> int:
        with self._lock:
            v = self._progress_raw
        return int(round(v * 100)) if 0.0 <= v <= 1.0 else int(round(v))

    def get_visual_timer(self) -> int:
        with self._lock:
            return self._visual_timer

    def get_rpm(self) -> int:
        with self._lock:
            return self._rpm

    def get_gear(self) -> int:
        with self._lock:
            return self._gear

    def get_velocity(self) -> float:
        """Return the current speed magnitude in km/h."""
        with self._lock:
            return self._velocity_raw

    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "ce_connected":    self._connected,
                "ce_reads_ok":     self.reads_ok,
                "ce_reads_failed": self.reads_failed,
                "visual_timer":    self._visual_timer,
                "rpm":             self._rpm,
                "gear":            self._gear,
                "velocity_raw":    self._velocity_raw,
                "steering_raw":    self._steering_raw,
            }

    # -----------------------------------------------------------------------
    # Hook installation
    # -----------------------------------------------------------------------

    def _attach(self) -> bool:
        """Open the game process and record the module base address."""
        try:
            self._pm     = pymem.Pymem(self.PROCESS_NAME)
            self._module = pymem.process.module_from_name(
                self._pm.process_handle, self.PROCESS_NAME
            )
            self._base = self._module.lpBaseOfDll
            print(f"[DataExtractor] Attached to {self.PROCESS_NAME} "
                  f"(base={self._base:#x})")
            return True
        except Exception as exc:
            self._pm = None
            self._last_fail_reason = f"attach_failed: {exc}"
            return False

    def _read_local_struct_offset(self) -> None:
        """
        Read the local player struct offset from the displacement embedded in the
        game instruction: mov rax,[rcx+NNNNNNNN]

        Scans for the fixed bytes that follow that instruction (cmp + setne), then
        reads the 4-byte little-endian displacement from match-4.  Falls back to
        0x90 (the typical value) if the scan fails.
        """
        try:
            match = self._aob_scan(self._AOB_LOCAL_STRUCT_OFFSET_CTX)
            if match is None:
                print("[DataExtractor] \u26a0 Local struct offset AOB not found \u2014 using default 0x90")
                self._local_struct_offset = 0x90
                return
            # The 10-byte pattern starts at `match`.
            # The 7-byte instruction before it ends at match-1, so its displacement
            # is at bytes match-4 through match-1 (4-byte little-endian DWORD).
            offset_val = self._pm.read_uint(match - 4)
            self._local_struct_offset = offset_val
            print(f"[DataExtractor] Local player struct offset = {offset_val:#x}")
        except Exception as exc:
            print(f"[DataExtractor] \u26a0 Could not read local struct offset: {exc} \u2014 using default 0x90")
            self._local_struct_offset = 0x90

    def _aob_scan(self, pattern: bytes) -> Optional[int]:
        """
        Scan for *pattern* (regex bytes) inside the game module.
        Returns the matched address, or None with _last_fail_reason set.
        """
        try:
            addr = pymem.pattern.pattern_scan_module(
                self._pm.process_handle,
                self._module,
                pattern,
            )
            if addr:
                return addr
            self._last_fail_reason = "pattern_not_found"
            return None
        except Exception as exc:
            self._last_fail_reason = f"scan_error: {exc}"
            return None

    def _aob_scan_near(self, pattern: bytes, near: int, window: int = 0x200000) -> Optional[int]:
        """
        Like _aob_scan but only searches within *window* bytes either side of *near*.

        Used for the VT fallback so that a whole-module scan can't accidentally
        match an unrelated occurrence of the same byte sequence elsewhere in the
        game binary.  Returns the matched absolute address, or None.
        """
        start  = max(near - window, self._base)
        length = min(near + window, self._base + self._module.SizeOfImage) - start
        if length <= 0:
            self._last_fail_reason = "near_window_out_of_range"
            return None
        try:
            mem = bytes(self._pm.read_bytes(start, length))
        except Exception as exc:
            self._last_fail_reason = f"near_read_error: {exc}"
            return None
        m = re.search(pattern, mem)
        if m:
            found = start + m.start()
            print(f"[DataExtractor]   near-scan found match @ {found:#x}  "
                  f"(offset {found - self._base:#x} from base, "
                  f"searched {start:#x}–{start+length:#x})")
            return found
        self._last_fail_reason = "pattern_not_found_in_window"
        return None

    def _write_patch(self, address: int, new_bytes: bytes, save_to: dict) -> None:
        """
        Write *new_bytes* at *address*, saving originals into *save_to*.
        Temporarily changes page protection to PAGE_EXECUTE_READWRITE.
        Caller is responsible for the game being in a safe state (frozen).
        """
        orig = bytes(self._pm.read_bytes(address, len(new_bytes)))
        save_to[address] = orig
        old_prot = _vprotect(
            self._pm.process_handle, address, len(new_bytes),
            PAGE_EXECUTE_READWRITE
        )
        self._pm.write_bytes(address, new_bytes, len(new_bytes))
        _vprotect(self._pm.process_handle, address, len(new_bytes), old_prot)

    def _restore_patches(self, saved: dict) -> None:
        """Restore original bytes for every address in *saved*."""
        for addr, orig in saved.items():
            try:
                old_prot = _vprotect(
                    self._pm.process_handle, addr, len(orig),
                    PAGE_EXECUTE_READWRITE
                )
                self._pm.write_bytes(addr, orig, len(orig))
                _vprotect(self._pm.process_handle, addr, len(orig), old_prot)
            except Exception as exc:
                print(f"[DataExtractor] ⚠ Could not restore {addr:#x}: {exc}")
        saved.clear()

    def _install_vt_hook(self) -> bool:
        """
        Install the permanent Visual Timer trampoline.

        Tries the static offset (base + 0x5CC82F) first; falls back to AOB
        scan if the bytes don't match (e.g. after a game update).

        Returns True on success.
        """
        handle = self._pm.process_handle

        inj = self._base + self._VT_STATIC_OFFSET
        print(f"[DataExtractor] VT hook: probing {inj:#x}  "
              f"(base={self._base:#x} + offset={self._VT_STATIC_OFFSET:#x})")

        try:
            actual = bytes(self._pm.read_bytes(inj, len(self._VT_EXPECTED)))
            print(f"[DataExtractor]   expected bytes : {self._VT_EXPECTED.hex(' ')}")
            print(f"[DataExtractor]   bytes on disk  : {actual.hex(' ')}")
        except Exception as exc:
            actual = b""
            print(f"[DataExtractor]   ✗ FATAL: read at {inj:#x} failed: {exc}")
            print( "[DataExtractor]     This usually means wrong base address or the "
                   "game module is not yet mapped. Cannot continue.")
            raise RuntimeError(
                f"[DataExtractor] VT probe read failed at {inj:#x}: {exc}"
            ) from exc

        # Check whether the static offset has been overwritten by a JMP (0xE9).
        # This happens when Cheat Engine's CT was active and then CE was closed
        # without disabling its scripts, leaving a dangling trampoline JMP in
        # the game's code.  We MUST NOT use the whole-module AOB fallback in
        # this case — the game binary contains other occurrences of the same
        # 9 bytes at different offsets (where ESI holds unrelated values), and
        # the scan would silently pick the wrong one.
        if actual[:1] == b"\xE9":
            raise RuntimeError(
                f"[DataExtractor] FATAL: VT hook site {inj:#x} contains a JMP (0x{actual[0]:02x}) — "
                "Cheat Engine left a stale patch in game memory.\n"
                "  Fix: open Cheat Engine, disable ALL scripts in the ALU table, "
                "then CLOSE Cheat Engine before running this program.\n"
                "  Alternatively, restart Asphalt 9 to restore original code."
            )

        if actual != self._VT_EXPECTED:
            print(
                f"[DataExtractor] ⚠ VT static offset MISMATCH at {inj:#x}\n"
                f"  Expected : {self._VT_EXPECTED.hex(' ')}\n"
                f"  Found    : {actual.hex(' ')}\n"
                f"  → Trying near-AOB fallback (search within ±2 MB of expected offset)…"
            )
            # Restrict the search to a ±2 MB window around the expected address.
            # This prevents matching an unrelated occurrence elsewhere in the module.
            fallback = self._aob_scan_near(self._AOB_VT, inj, window=0x200000)
            if fallback:
                inj = fallback
                refound = bytes(self._pm.read_bytes(inj, len(self._VT_EXPECTED)))
                print(f"[DataExtractor] ✓ VT found via near-AOB @ {inj:#x}")
                print(f"[DataExtractor]   AOB bytes : {refound.hex(' ')}")
            else:
                raise RuntimeError(
                    f"[DataExtractor] FATAL: VT instruction not found near expected offset "
                    f"(reason: {self._last_fail_reason}).\n"
                    "  The game may have been updated. Update _VT_STATIC_OFFSET and "
                    "_VT_EXPECTED to match the current game version."
                )
        else:
            print(f"[DataExtractor] ✓ VT static bytes match")

        alloc = _valloc_near(handle, inj)
        self._alloc_vt = alloc
        print(f"[DataExtractor] VT stub page allocated @ {alloc:#x}  "
              f"(data area = {alloc:#x}, code area = {alloc + _CODE_OFFSET:#x})")

        stub  = _build_vt_stub(alloc, inj + 9)
        self._pm.write_bytes(alloc, stub, len(stub))
        print(f"[DataExtractor] VT stub written ({len(stub)} bytes)")

        patch = _jmp_rel32(inj, alloc + _CODE_OFFSET) + b"\x90\x90\x90\x90"
        print(f"[DataExtractor] Writing VT patch @ {inj:#x}: {patch.hex(' ')}")
        self._write_patch(inj, patch, self._saved_vt)

        # Verify patch landed correctly — a mismatch means write failed silently.
        try:
            verify = bytes(self._pm.read_bytes(inj, len(patch)))
            if verify == patch:
                print(f"[DataExtractor] ✓ VT patch verified @ {inj:#x}")
            else:
                print(f"[DataExtractor] ✗ VT patch VERIFY MISMATCH @ {inj:#x}!")
                print(f"  wrote  : {patch.hex(' ')}")
                print(f"  on-disk: {verify.hex(' ')}")
                print( "  VT hook likely did NOT apply — check process permissions.")
                return False
        except Exception as exc:
            print(f"[DataExtractor] ⚠ Could not re-read VT patch for verification: {exc}")

        self._inj_vt       = inj
        self._vt_installed = True
        print(f"[DataExtractor] ✓ VT hook (permanent) installed @ {inj:#x} "
              f"→ stub @ {alloc + _CODE_OFFSET:#x}, data @ {alloc:#x}")
        print( "[DataExtractor]   ESI at that instruction = VisualTimer value")
        print( "[DataExtractor]   Expected: exactly 1,000,000 in menus; exactly 0 at countdown start")
        return True

    def _remove_vt_hook(self) -> None:
        """Remove the permanent VT hook and free its allocation."""
        if not self._pm:
            return
        if self._saved_vt:
            self._restore_patches(self._saved_vt)
        if self._alloc_vt:
            try:
                _vfree(self._pm.process_handle, self._alloc_vt)
            except Exception:
                pass
            self._alloc_vt     = None
        self._inj_vt       = None
        self._vt_installed = False

    def _install_steering_hook(self) -> bool:
        """
        Install the permanent steering input trampoline.

        Scans for the movss [rsi+0x1540],xmm1 instruction and hooks it to
        capture the steering input float at rsi+0x1544 every frame.
        Returns True on success.
        """
        if not self._pm:
            return False
        handle = self._pm.process_handle

        inj = self._aob_scan(self._AOB_STEERING)
        if inj is None:
            print(f"[DataExtractor] \u26a0 Steering AOB not found — steering display unavailable "
                  f"(reason: {self._last_fail_reason})")
            return False

        print(f"[DataExtractor] Steering hook: installing at {inj:#x}")
        alloc = _valloc_near(handle, inj)
        self._alloc_steering = alloc

        stub = _build_steering_stub(alloc, inj + 8)
        self._pm.write_bytes(alloc, stub, len(stub))

        patch = _jmp_rel32(inj, alloc + _CODE_OFFSET) + b"\x90\x90\x90"
        self._write_patch(inj, patch, self._saved_steering)

        self._inj_steering       = inj
        self._steering_installed = True
        print(f"[DataExtractor] \u2713 Steering hook (permanent) installed @ {inj:#x} "
              f"\u2192 stub @ {alloc + _CODE_OFFSET:#x}, data @ {alloc:#x}")
        return True

    def _remove_steering_hook(self) -> None:
        """Remove the permanent steering hook and free its allocation."""
        if not self._pm:
            return
        if self._saved_steering:
            self._restore_patches(self._saved_steering)
        if self._alloc_steering:
            try:
                _vfree(self._pm.process_handle, self._alloc_steering)
            except Exception:
                pass
            self._alloc_steering     = None
        self._inj_steering       = None
        self._steering_installed = False

    def _emergency_remove_temp_hooks(self) -> None:
        """
        Restore any live temporary JMP patches and free orphaned stub pages.

        Called from stop() so that the game binary is left clean when the
        program exits, even if it is closed mid-capture or while a deferred
        progress hook is still active.  Without this, restarting the tool
        finds modified bytes at the hook sites instead of the expected AOB
        patterns, causing fatal errors on the next AOB scan.
        """
        if not self._pm:
            return

        patches_to_restore: dict = {}

        # Any patches from the main capture cycle that weren't cleaned up yet
        # (e.g. program closed during Step 4 poll while JMP patches were live).
        if self._live_temp_patches:
            patches_to_restore.update(self._live_temp_patches)

        # Deferred progress patch — left live after fast exit, pending background thread.
        if self._deferred_prog_inj and self._deferred_prog_orig:
            patches_to_restore[self._deferred_prog_inj] = self._deferred_prog_orig

        if patches_to_restore:
            print(f"[DataExtractor] Emergency cleanup: restoring "
                  f"{len(patches_to_restore)} live JMP patch(es)…")
            try:
                pid = self._pm.process_id
                th  = _freeze_threads(pid)
                try:
                    self._restore_patches(patches_to_restore)
                finally:
                    _unfreeze_threads(th)
                print("[DataExtractor] Emergency cleanup: all patches restored.")
            except Exception as exc:
                print(f"[DataExtractor] ⚠ Emergency cleanup error: {exc}")
            self._live_temp_patches = {}

        # Free any orphaned stub pages (alloc1/2 freed in Step 8, alloc3 may
        # remain if deferred capture was still running at exit).
        allocs_to_free = list(self._live_temp_allocs)
        if self._deferred_prog_alloc:
            allocs_to_free.append(self._deferred_prog_alloc)
        for alloc in allocs_to_free:
            try:
                _vfree(self._pm.process_handle, alloc)
            except Exception:
                pass

        self._live_temp_allocs    = []
        self._deferred_prog_alloc = None
        self._deferred_prog_inj   = None
        self._deferred_prog_orig  = None

    # -----------------------------------------------------------------------
    # Pre-scan helpers + freeze-capture cycle (temporary hooks 1–3)
    # -----------------------------------------------------------------------

    def _run_prescan(self) -> None:
        """
        Background pre-scan: Steps 1+2 of the capture cycle.
        Triggered by VT: 1M → 0 (countdown start) so that when the race
        actually begins, _capture_addresses() only needs Steps 3–8
        (≈5 ms freeze + ≤500 ms poll instead of waiting ~2 s for progress).

        AOB addresses are cached in _cached_injs after the first scan since
        the game binary does not change between races.
        """
        try:
            if not self._pm:
                return
            handle = self._pm.process_handle

            # Step 1: AOB scan — use cache if available; binary is stable.
            if not self._cached_injs:
                inj1     = self._aob_scan(self._AOB_DASHBOARD)
                inj2_ctx = self._aob_scan(self._AOB_TIMER_CTX)
                inj3     = self._aob_scan(self._AOB_PROGRESS)
                if not (inj1 and inj2_ctx and inj3):
                    print("[DataExtractor] Pre-scan: AOB scan failed — "
                          "will retry at race start")
                    return
                inj2 = inj2_ctx + self._AOB_TIMER_HOOK_OFFSET
                self._cached_injs = {1: inj1, 2: inj2, 3: inj3}
                print(f"[DataExtractor] Pre-scan: AOB cached — "
                      f"dash={inj1:#x} timer={inj2:#x} prog={inj3:#x}")
            else:
                inj1, inj2, inj3 = (self._cached_injs[k] for k in (1, 2, 3))
                print("[DataExtractor] Pre-scan: using cached AOB addresses")

            # Step 2: alloc + write stubs
            alloc1 = _valloc_near(handle, inj1)
            alloc2 = _valloc_near(handle, inj2)
            alloc3 = _valloc_near(handle, inj3)
            if not (alloc1 and alloc2 and alloc3):
                print("[DataExtractor] Pre-scan: valloc failed — "
                      "will retry at race start")
                for a in (alloc1, alloc2, alloc3):
                    if a:
                        try: _vfree(handle, a)
                        except Exception: pass
                return
            stub1 = _build_dashboard_stub(alloc1, inj1 + 8)
            stub2 = _build_timer_stub    (alloc2, inj2 + 7)
            stub3 = _build_progress_stub (alloc3, inj3 + 6)
            self._pm.write_bytes(alloc1, stub1, len(stub1))
            self._pm.write_bytes(alloc2, stub2, len(stub2))
            self._pm.write_bytes(alloc3, stub3, len(stub3))
            with self._prescan_lock:
                self._prescan_allocs = {1: alloc1, 2: alloc2, 3: alloc3}
                self._prescan_ready  = True
            print(f"[DataExtractor] Pre-scan complete: "
                  f"alloc1={alloc1:#x} alloc2={alloc2:#x} alloc3={alloc3:#x}")
        except Exception as exc:
            print(f"[DataExtractor] Pre-scan exception: {exc}")

    def _deferred_progress_capture(self) -> None:
        """
        Background thread: wait for the progress hook stub to fire, capture
        _rdi_progress, then restore the JMP patch at inj3 and free the alloc.

        Only launched when _capture_addresses() takes the fast exit (dash+timer
        captured before the progress stub fires).  The JMP patch at the progress
        hook site remains live during this window — same anti-cheat exposure as
        the original design that waited ~2 s for progress.
        """
        alloc3 = self._deferred_prog_alloc
        inj3   = self._deferred_prog_inj
        orig3  = self._deferred_prog_orig
        if not (alloc3 and inj3 and orig3):
            return

        t0 = time.monotonic()
        print("[DataExtractor] Deferred progress capture: waiting for hook to fire…")
        captured = False
        while time.monotonic() - t0 < 10.0:
            try:
                prog_rdi = self._pm.read_ulonglong(alloc3 + 4)
                if prog_rdi > 0x10000:
                    self._rdi_progress = prog_rdi
                    print(f"[DataExtractor] ✓ Deferred progress: {prog_rdi:#x} "
                          f"({time.monotonic() - t0:.2f}s after fast exit)")
                    captured = True
                    break
            except Exception as exc:
                print(f"[DataExtractor] ⚠ Deferred progress poll error: {exc}")
                break
            time.sleep(0.01)

        if not captured:
            print("[DataExtractor] ⚠ Deferred progress: hook did not fire within 10 s "
                  "— progress will read 0.0 for this race")

        # Restore progress JMP patch (freeze for safety) and free stub page
        try:
            pid = self._pm.process_id
            th  = _freeze_threads(pid)
            try:
                saved = {inj3: orig3}
                self._restore_patches(saved)
            finally:
                _unfreeze_threads(th)
        except Exception as exc:
            print(f"[DataExtractor] ⚠ Deferred progress restore: {exc}")
        try:
            _vfree(self._pm.process_handle, alloc3)
        except Exception:
            pass

        self._deferred_prog_alloc = None
        self._deferred_prog_inj   = None
        self._deferred_prog_orig  = None

    def _capture_addresses(self) -> bool:
        """
        Freeze-inject-fire-freeze-remove cycle to capture rdi bases.

        Steps 1+2 are normally pre-run in _run_prescan() during the countdown.
        If pre-scan isn't ready, they run inline as a fallback.

        Step 1 (no freeze):   AOB scan (or use cache / prescan result).
        Step 2 (no freeze):   alloc stub pages + write stub code (or use prescan).
        Step 3 (FREEZE):      Patch hook sites with JMP bytes.
        Step 4 (UNFREEZE):    Game runs; stubs fire.
                              Fast exit: break when dash+timer both captured (~0.5 s);
                                progress deferred to background thread.
                              Full exit: break when progress hook fires (~1.9 s).
        Step 5 (FREEZE):      Read captured rdi pointers from stub data areas.
        Step 6 (still frozen): Restore dash+timer patches; restore progress only
                              if already captured — else defer.
        Step 7 (UNFREEZE):    Game resumes. Only deferred progress JMP may remain.
        Step 8 (no freeze):   Free alloc1+2; free alloc3 only if not deferred.
                              Launch _deferred_progress_capture() if deferred.

        Returns True if at least rdi_dash and rdi_timer were captured.
        """
        handle = self._pm.process_handle
        pid    = self._pm.process_id

        # ── Steps 1+2: use pre-scan result or fall back to inline ─────────
        with self._prescan_lock:
            prescan_ready  = self._prescan_ready
            prescan_allocs = dict(self._prescan_allocs)
            self._prescan_ready  = False
            self._prescan_allocs = {}

        if prescan_ready and self._cached_injs:
            inj1   = self._cached_injs[1]
            inj2   = self._cached_injs[2]
            inj3   = self._cached_injs[3]
            alloc1 = prescan_allocs[1]
            alloc2 = prescan_allocs[2]
            alloc3 = prescan_allocs[3]
            print(f"[DataExtractor] [Steps 1-2/8] Using pre-scanned stubs — "
                  f"dash@{inj1:#x}→{alloc1:#x}, "
                  f"timer@{inj2:#x}→{alloc2:#x}, "
                  f"prog@{inj3:#x}→{alloc3:#x}")
        else:
            print("[DataExtractor] [Steps 1-2/8] Pre-scan not ready — running inline")
            if self._cached_injs:
                inj1 = self._cached_injs[1]
                inj2 = self._cached_injs[2]
                inj3 = self._cached_injs[3]
                print(f"[DataExtractor]   Cached AOBs: "
                      f"dash={inj1:#x}, timer={inj2:#x}, prog={inj3:#x}")
            else:
                inj1 = self._aob_scan(self._AOB_DASHBOARD)
                if not inj1:
                    print(f"[DataExtractor] ✗ Dashboard AOB not found "
                          f"({self._last_fail_reason})")
                    return False
                inj2_ctx = self._aob_scan(self._AOB_TIMER_CTX)
                if not inj2_ctx:
                    print(f"[DataExtractor] ✗ Timer AOB not found "
                          f"({self._last_fail_reason})")
                    return False
                inj2 = inj2_ctx + self._AOB_TIMER_HOOK_OFFSET
                inj3 = self._aob_scan(self._AOB_PROGRESS)
                if not inj3:
                    print(f"[DataExtractor] ✗ Progress AOB not found "
                          f"({self._last_fail_reason})")
                    return False
                self._cached_injs = {1: inj1, 2: inj2, 3: inj3}
                print(f"[DataExtractor]   AOB scan: "
                      f"dash={inj1:#x}, timer={inj2:#x}, prog={inj3:#x}")
            alloc1 = _valloc_near(handle, inj1)
            alloc2 = _valloc_near(handle, inj2)
            alloc3 = _valloc_near(handle, inj3)
            stub1 = _build_dashboard_stub(alloc1, inj1 + 8)
            stub2 = _build_timer_stub    (alloc2, inj2 + 7)
            stub3 = _build_progress_stub (alloc3, inj3 + 6)
            self._pm.write_bytes(alloc1, stub1, len(stub1))
            self._pm.write_bytes(alloc2, stub2, len(stub2))
            self._pm.write_bytes(alloc3, stub3, len(stub3))
            print(f"[DataExtractor]   Stubs written: "
                  f"dash={len(stub1)}B@{alloc1:#x}, "
                  f"timer={len(stub2)}B@{alloc2:#x}, "
                  f"prog={len(stub3)}B@{alloc3:#x}")

        # ── Hook 5 (Local Player Ptr): always freshly allocated ───────────
        # Scan for inj4 (cached after first scan); alloc4 is never prescanned.
        inj4:   Optional[int] = None
        alloc4: Optional[int] = None
        if 4 not in self._cached_injs:
            _inj4 = self._aob_scan(self._AOB_LOCAL_PLAYER_PTR)
            if _inj4:
                self._cached_injs[4] = _inj4
                print(f"[DataExtractor] Hook 5 (local player ptr) AOB @ {_inj4:#x}")
            else:
                print("[DataExtractor] \u26a0 Local player ptr AOB not found \u2014 velocity unavailable")
        if 4 in self._cached_injs:
            inj4 = self._cached_injs[4]
        if inj4:
            try:
                alloc4 = _valloc_near(handle, inj4)
                stub4  = _build_local_player_stub(alloc4, inj4 + 13)
                self._pm.write_bytes(alloc4, stub4, len(stub4))
                print(f"[DataExtractor] Hook 5 stub: {len(stub4)}B @ {alloc4:#x}")
            except Exception as exc:
                print(f"[DataExtractor] \u26a0 Hook 5 alloc/write failed: {exc} \u2014 velocity unavailable")
                if alloc4:
                    try: _vfree(handle, alloc4)
                    except Exception: pass
                alloc4 = None

        # ── Step 3: (optionally FREEZE) + patch ──────────────────────────
        saved_temp: dict = {}
        print(f"[DataExtractor] [Step 3/8] FREEZE_FOR_CAPTURE={self.FREEZE_FOR_CAPTURE}")
        if self.FREEZE_FOR_CAPTURE:
            thread_handles = _freeze_threads(pid)
            if not thread_handles:
                print("[DataExtractor]   ✗ FATAL: _freeze_threads returned 0 handles — "
                      "could not freeze any game threads. Check process permissions.")
                for a in (alloc1, alloc2, alloc3, alloc4):
                    if a:
                        try: _vfree(handle, a)
                        except Exception: pass
                raise RuntimeError("[DataExtractor] _freeze_threads returned 0 handles")
            print(f"[DataExtractor]   Game frozen ({len(thread_handles)} threads suspended)")
        else:
            thread_handles = []
            print("[DataExtractor]   ⚠ FREEZE_FOR_CAPTURE=False — patching live (dev mode)")

        p1 = _jmp_rel32(inj1, alloc1 + _CODE_OFFSET) + b"\x90\x90\x90"
        p2 = _jmp_rel32(inj2, alloc2 + _CODE_OFFSET) + b"\x90\x90"
        p3 = _jmp_rel32(inj3, alloc3 + _CODE_OFFSET) + b"\x90"
        print(f"[DataExtractor]   patch bytes:")
        print(f"    dash  @ {inj1:#x}: {p1.hex(' ')}")
        print(f"    timer @ {inj2:#x}: {p2.hex(' ')}")
        print(f"    prog  @ {inj3:#x}: {p3.hex(' ')}")

        try:
            self._write_patch(inj1, p1, saved_temp)
            self._write_patch(inj2, p2, saved_temp)
            self._write_patch(inj3, p3, saved_temp)
            if alloc4 and inj4:
                p4 = _jmp_rel32(inj4, alloc4 + _CODE_OFFSET) + b"\x90" * 8  # 5+8=13 bytes
                self._write_patch(inj4, p4, saved_temp)
                print(f"    localp@ {inj4:#x}: {p4.hex(' ')}")
            print(f"[DataExtractor]   ✓ All {len(saved_temp)} patches written successfully")
            # Track for emergency cleanup on stop() — cleared in Steps 6+8
            self._live_temp_patches = dict(saved_temp)
            self._live_temp_allocs  = [a for a in (alloc1, alloc2, alloc3, alloc4) if a]
        except Exception as exc:
            if self.FREEZE_FOR_CAPTURE:
                _unfreeze_threads(thread_handles)
            self._restore_patches(saved_temp)
            for a in (alloc1, alloc2, alloc3, alloc4):
                if a:
                    try: _vfree(handle, a)
                    except Exception: pass
            raise RuntimeError(f"[DataExtractor] FATAL: patch write failed: {exc}") from exc

        # ── Step 4: UNFREEZE — let hooks fire ────────────────────────────
        print(f"[DataExtractor] [Step 4/8] Unfreezing — hooks now live")
        if self.FREEZE_FOR_CAPTURE:
            _unfreeze_threads(thread_handles)
            thread_handles = []

        # Fast-exit: leave as soon as dash+timer are both captured (~0.5 s).
        # Progress fires at ~1.9 s; capture it in a background thread so the
        # main loop gets timer/rpm/gear within ≈500 ms.
        # Full-exit: if progress fires first (fast machine / already warmed), use it.
        print(f"[DataExtractor] Polling: fast exit on dash+timer, "
              f"full exit on progress, cap={self._CAPTURE_SAFETY_TIMEOUT_S:.0f}s")

        t0             = time.monotonic()
        _next_poll_log = t0 + 0.5
        rdi_captured   = False
        fast_exit      = False
        capture_aborted = False
        while True:
            try:
                vt_now = self._pm.read_uint(self._alloc_vt)

                # Abort if user quit to menus before hooks fired.
                if vt_now == 1_000_000:
                    print(f"[DataExtractor]   ✗ VT returned to 1M — "
                          f"user quit before hooks fired. Aborting capture.")
                    capture_aborted = True
                    break

                prog_rdi   = self._pm.read_ulonglong(alloc3 + 4)
                dash_rdi   = self._pm.read_ulonglong(alloc1 + 12)
                timer_rdi  = self._pm.read_ulonglong(alloc2 + 8)
                lp_ptr_raw = self._pm.read_ulonglong(alloc4) if alloc4 else 0
                now     = time.monotonic()
                elapsed = now - t0
                if now >= _next_poll_log:
                    print(f"[DataExtractor]   polling @ {elapsed:.1f}s: "
                          f"prog_rdi={prog_rdi:#x}  dash_rdi={dash_rdi:#x}  "
                          f"timer_rdi={timer_rdi:#x}  lp_ptr={lp_ptr_raw:#x}  vt={vt_now}")
                    _next_poll_log = now + 0.5

                # Fast exit: dash+timer+lp_ptr all available (elapsed ≥ 0.1 s).
                # Deferred progress if not yet fired.
                lp_ready = (alloc4 is None) or (lp_ptr_raw > 0x10000)
                if dash_rdi > 0x10000 and timer_rdi > 0x10000 and lp_ready and elapsed >= 0.1:
                    rdi_captured = True
                    fast_exit    = prog_rdi <= 0x10000
                    label = "fast exit — deferring progress" if fast_exit else "full exit"
                    print(f"[DataExtractor]   ✓ Dash+timer+lp_ptr captured ({label}, "
                          f"{elapsed:.2f}s after unfreeze)")
                    break

                # Safety fallback: 5 s
                if elapsed >= 5.0 and (dash_rdi > 0x10000 or timer_rdi > 0x10000):
                    rdi_captured = True
                    fast_exit    = prog_rdi <= 0x10000
                    print(f"[DataExtractor]   ⚠ 5 s elapsed — proceeding with "
                          f"available captures")
                    break

            except Exception as exc:
                print(f"[DataExtractor]   ⚠ read error during wait: {exc}")

            if time.monotonic() - t0 > self._CAPTURE_SAFETY_TIMEOUT_S:
                print(f"[DataExtractor]   ✗ Safety timeout "
                      f"({self._CAPTURE_SAFETY_TIMEOUT_S:.0f}s) reached.")
                break

            time.sleep(0.001)

        if not rdi_captured and not capture_aborted:
            print(f"[DataExtractor] ⚠ rdi not captured — hooks did not fire.")
            print( "    • Hook sites wrong (game update)?")
            print( "    • JMP patch not written correctly?")

        # ── Step 5+6: (optionally FREEZE) → read pointers → restore patches
        print(f"[DataExtractor] [Step 5/8] Re-freezing to read captured pointers…")
        if self.FREEZE_FOR_CAPTURE:
            thread_handles = _freeze_threads(pid)
            print(f"[DataExtractor]   Re-frozen ({len(thread_handles)} threads)")
        else:
            thread_handles = []

        rdi_progress: Optional[int] = None
        rdi_dash:     Optional[int] = None
        rdi_timer:    Optional[int] = None
        local_player_ptr: Optional[int] = None

        try:
            _prog  = self._pm.read_ulonglong(alloc3 + 4)
            _timer = self._pm.read_ulonglong(alloc2 + 8)
            _dash  = self._pm.read_ulonglong(alloc1 + 12)
            if _prog > 0x10000:
                rdi_progress = _prog
                print(f"[DataExtractor] ✓ rdi_progress = {_prog:#x}  (progress @ +0x1D8)")
            else:
                print(f"[DataExtractor]   rdi_progress not yet captured "
                      f"({_prog:#x}) — will defer")
            if _dash > 0x10000:
                rdi_dash = _dash
                print(f"[DataExtractor] ✓ rdi_dash     = {_dash:#x}  "
                      f"(rpm @ +0x1B8, gear @ +0xA0)")
            else:
                print(f"[DataExtractor] ✗ rdi_dash not captured ({_dash:#x})")
            if _timer > 0x10000:
                rdi_timer = _timer
                print(f"[DataExtractor] ✓ rdi_timer    = {_timer:#x}  (timer @ +0x10)")
            else:
                print(f"[DataExtractor] ✗ rdi_timer not captured ({_timer:#x})")
            if alloc4:
                _lp = self._pm.read_ulonglong(alloc4)
                if _lp > 0x10000:
                    local_player_ptr = _lp
                    print(f"[DataExtractor] ✓ local_player_ptr = {_lp:#x}  "
                          f"(velocity @ player_base+0x160/164/168)")
                else:
                    print(f"[DataExtractor] ⚠ local_player_ptr not captured ({_lp:#x})")
        except Exception as exc:
            print(f"[DataExtractor] ✗ Failed to read captured rdis: {exc}")

        # Restore dash+timer+local_player patches unconditionally.
        # For progress: restore only if already captured; if deferred, leave the
        # JMP patch active so the background thread can still use the stub.
        prog_orig_bytes = saved_temp.pop(inj3, None)   # remove from dict, keep value
        self._restore_patches(saved_temp)              # restores dash + timer + local_player
        if rdi_progress is not None:
            # Progress captured — restore its patch too
            if prog_orig_bytes:
                self._restore_patches({inj3: prog_orig_bytes})
            deferred = False
        else:
            # Deferred: leave JMP patch at inj3 live for background thread
            deferred = True
        total_patched = 4 if (alloc4 and inj4) else 3
        _prog_label = f"{total_patched-1}/{total_patched} — progress deferred" if deferred else f"{total_patched}/{total_patched}"
        print(f"[DataExtractor] [Step 6/8] Patches restored ({_prog_label})")
        # Non-deferred patches are no longer live; clear from emergency tracker.
        # Deferred patch (if any) is tracked via _deferred_prog_inj/_orig instead.
        self._live_temp_patches = {}

        # ── Step 7: UNFREEZE permanently ─────────────────────────────────
        print("[DataExtractor] [Step 7/8] Unfreezing game permanently…")
        if self.FREEZE_FOR_CAPTURE:
            _unfreeze_threads(thread_handles)
        print("[DataExtractor] Game unfrozen"
              + (" (progress JMP still live until deferred capture completes)"
                 if deferred else " — zero temporary hooks active"))

        # ── Step 8: Free stubs / launch deferred thread ──────────────────
        for alloc in (alloc1, alloc2, alloc4):  # alloc4 never deferred
            if alloc:
                try: _vfree(handle, alloc)
                except Exception: pass

        if deferred:
            self._deferred_prog_alloc = alloc3
            self._deferred_prog_inj   = inj3
            self._deferred_prog_orig  = prog_orig_bytes
            threading.Thread(target=self._deferred_progress_capture,
                             daemon=True).start()
        else:
            try: _vfree(handle, alloc3)
            except Exception: pass
        self._live_temp_allocs = []   # alloc1+2 freed above; alloc3 freed or deferred

        if rdi_dash and rdi_timer:
            self._rdi_dash    = rdi_dash
            self._rdi_timer   = rdi_timer
            if rdi_progress:
                self._rdi_progress = rdi_progress
            if local_player_ptr:
                self._local_player_ptr_val = local_player_ptr
            self._direct_mode = True
            print(f"[DataExtractor] Direct-read mode active"
                  + (f", velocity available (lp_ptr={local_player_ptr:#x})" if local_player_ptr else ", velocity unavailable (lp_ptr not captured)"))
            return True
        else:
            return False

    # -----------------------------------------------------------------------
    # Synchronous read — called from the main loop each tick
    # -----------------------------------------------------------------------

    def read(self) -> Union[dict, bool]:
        """
        Synchronous read called by the main loop every tick.

        Returns a dict of all current telemetry values if ANY value has
        changed since the last call, or False if nothing changed / not ready.

        Internally manages lazy attach, VT hook installation, and the
        freeze-capture cycle:

          • Not attached        → try _attach(), return False
          • VT hook not ready   → try _install_vt_hook(), return False
          • VT: 1,000,000 → 0  → call _capture_addresses() (blocks
                                  ~countdown duration), then continue
          • VT returns to 1M   → invalidate rdi/r13 bases
          • direct_mode active  → read all values from rdi_progress / rdi_dash / rdi_timer
          • not direct_mode     → read only VT from permanent stub
          • No change detected  → return False  (main loop skips)

        Return dict keys (same as get_all_values):
          timer_raw, progress, rpm, gear, visual_timer
        """
        # ── 1. Ensure attached ─────────────────────────────────────────
        if self._pm is None:
            if not self._attach():
                return False

        # ── 2. Ensure VT hook installed ────────────────────────────────
        if not self._vt_installed:
            if not self._install_vt_hook():
                return False

        # ── 3. Read Visual Timer from permanent stub ───────────────────
        try:
            current_vt: int = self._pm.read_uint(self._alloc_vt)
        except Exception as exc:
            self._last_fail_reason = str(exc)
            self.reads_failed += 1
            # Process likely died — force full re-attach next call
            print(f"[DataExtractor] ✗ VT read failed (stub @ {self._alloc_vt:#x}): {exc} "
                   "— forcing re-attach")
            self._remove_vt_hook()
            self._pm = None
            with self._lock:
                self._connected = False
            return False

        # Periodic VT diagnostic — print every 2 s so we can see what the hook captures.
        _now_ts = time.time()
        if _now_ts - self._last_vt_log >= 2.0:
            #print(f"[DataExtractor] VT tick: raw={current_vt}  prev={self._prev_vt}  "
            #      f"direct_mode={self._direct_mode}  "
            #      f"stub_addr={self._alloc_vt:#x}")
            if current_vt not in (0, 1_000_000) and not (current_vt > 0x10000):
                print(f"[DataExtractor]   ⚠ VT={current_vt} is unexpectedly small — "
                       "expected exactly 1,000,000 in menus or a large counter in-race.")
                print( "[DataExtractor]   This means ESI at the hook site does not hold VT.")
                print( "[DataExtractor]   The hook may be at the wrong address (game update?).")
            self._last_vt_log = _now_ts

        # ── 3b. Pre-scan trigger: VT 1M → 0 (countdown start) ────────────
        # Launch background Steps 1+2 (AOB scan + alloc + write stubs) so
        # that when the race actually starts the capture only needs Steps 3-8.
        if self._prev_vt == 1_000_000 and current_vt == 0:
            print("[DataExtractor] Countdown detected — starting background pre-scan")
            with self._prescan_lock:
                self._prescan_ready  = False
                self._prescan_allocs = {}
            threading.Thread(target=self._run_prescan, daemon=True).start()

        # ── 4. Capture trigger: VT 0 → >0 (race actually started) ────────
        # We intentionally do NOT trigger on VT: 1M → 0 (countdown), because
        # during the countdown the game hasn't started updating the player's
        # race-manager struct yet.  The progress hook (mov [rdi+0x1D8],eax)
        # only executes once the race timer is running (VT > 0).
        # Triggering here guarantees the progress hook fires within 1-2 frames.
        if self._prev_vt == 0 and 0 < current_vt < 1_000_000:
            print(f"[DataExtractor] ✓ Race started (VT: 0 → {current_vt}) — "
                  "starting freeze-capture cycle…")
        if self._prev_vt == 0 and 0 < current_vt < 1_000_000:
            self._direct_mode  = False
            self._rdi_progress = None
            self._rdi_dash     = None
            self._rdi_timer    = None
            self._local_player_ptr_val = None
            ok = self._capture_addresses()
            if not ok:
                print("[DataExtractor] Capture failed — "
                      "direct-read unavailable for this race")
            # Fall through: return current snapshot so main loop sees VT=0

        # ── 5. Invalidate on return to menus ───────────────────────────
        if current_vt == 1_000_000 and self._direct_mode:
            self._direct_mode  = False
            self._rdi_progress = None
            self._rdi_dash     = None
            self._rdi_timer    = None
            self._local_player_ptr_val = None
            self._first_read_logged = False
            print("[DataExtractor] Returned to menus — direct-read mode cleared")

        # ── 6. Read telemetry values ───────────────────────────────────
        timer_raw:    int   = 0
        progress:     float = 0.0
        rpm:          int   = 1250
        gear:         int   = 0
        velocity_raw: float = 0.0
        steering_raw: float = 0.0

        # Read steering from permanent stub (always active when installed)
        if self._steering_installed and self._alloc_steering:
            try:
                s = self._pm.read_float(self._alloc_steering)
                # Clamp and sanitise — catch NaN/Inf from uninitialised stub memory
                if -2.0 <= s <= 2.0:
                    steering_raw = max(-1.0, min(1.0, s))
            except Exception:
                pass

        if self._direct_mode:
            try:
                pm = self._pm
                # Each field uses the rdi from its own hook — they point to
                # different game objects with different struct layouts.
                if self._rdi_timer:
                    timer_raw = pm.read_uint(self._rdi_timer + 0x10)
                if self._rdi_progress:
                    progress  = pm.read_float(self._rdi_progress + 0x1D8)
                if self._rdi_dash:
                    rpm  = int(pm.read_float(self._rdi_dash + 0x1B8))  # cvttss2si truncate
                    gear = pm.read_uint(self._rdi_dash + 0xA0)
                if self._local_player_ptr_val and self._local_struct_offset:
                    player_base = pm.read_ulonglong(
                        self._local_player_ptr_val + self._local_struct_offset
                    )
                    vx = pm.read_float(player_base + 0x160)
                    vz = pm.read_float(player_base + 0x164)
                    vy = pm.read_float(player_base + 0x168)
                    velocity_raw = math.sqrt(vx*vx + vz*vz + vy*vy)
            except Exception as exc:
                self._last_fail_reason = str(exc)
                self.reads_failed += 1
                # Struct freed between races — re-capture on next race start
                self._direct_mode  = False
                self._rdi_progress = None
                self._rdi_dash     = None
                self._rdi_timer    = None
                self._local_player_ptr_val = None
                self._prev_vt = current_vt
                with self._lock:
                    self._connected = False
                return False

        # ── 7. Change detection ────────────────────────────────────────
        # Only trigger on timer_raw or visual_timer changes.  timer_raw
        # increments on every game data frame during a race; visual_timer
        # handles menus / pre-race state transitions.  Progress, rpm, and
        # gear are NOT used for change detection — they are picked up in
        # the stabilised second read below.
        prev         = self._prev_vals
        prev_timer   = prev["timer_raw"]    if prev else None
        prev_vt_val  = prev["visual_timer"] if prev else None
        changed      = (prev is None) or (timer_raw != prev_timer) or (current_vt != prev_vt_val)
        self._prev_vt = current_vt

        if not changed:
            return False
        prev_velocity = prev["velocity_raw"] if prev else None
        prev_rpm      = prev["rpm"]          if prev else None
        prev_gear     = prev["gear"]         if prev else None
        changed = (prev is None) or (velocity_raw != prev_velocity) or (rpm != prev_rpm) or (gear != prev_gear)
        # ── 7b. Stabilising second read ───────────────────────────────
        # Sleep 1 ms so the game engine has time to finish writing all
        # fields for the current frame, then re-read everything.  This
        # ensures timer_raw, progress, rpm, and gear are all from the
        # same game update rather than a mix of two adjacent frames.
        # If the second read fails, fall back to first-read values.
        time.sleep(0.001)
        if self._direct_mode:
            try:
                pm = self._pm
                if self._rdi_timer:
                    timer_raw = pm.read_uint(self._rdi_timer + 0x10)
                if self._rdi_progress:
                    progress  = pm.read_float(self._rdi_progress + 0x1D8)
                if self._rdi_dash:
                    rpm  = int(pm.read_float(self._rdi_dash + 0x1B8))
                    gear = pm.read_uint(self._rdi_dash + 0xA0)
                if self._local_player_ptr_val and self._local_struct_offset:
                    player_base = pm.read_ulonglong(
                        self._local_player_ptr_val + self._local_struct_offset
                    )
                    vx = pm.read_float(player_base + 0x160)
                    vz = pm.read_float(player_base + 0x164)
                    vy = pm.read_float(player_base + 0x168)
                    velocity_raw = math.sqrt(vx*vx + vz*vz + vy*vy)
                current_vt = self._pm.read_uint(self._alloc_vt)
                if self._steering_installed and self._alloc_steering:
                    try:
                        s = self._pm.read_float(self._alloc_steering)
                        if -2.0 <= s <= 2.0:
                            steering_raw = max(-1.0, min(1.0, s))
                    except Exception:
                        pass
            except Exception:
                pass  # keep first-read values if second read fails

        new_vals = {
            "timer_raw":    timer_raw,
            "progress":     progress,
            "rpm":          rpm,
            "gear":         gear,
            "visual_timer": current_vt,
            "velocity_raw": velocity_raw,
            "steering_raw": steering_raw,
            "physics_update": changed
        }
        self._prev_vals = new_vals

        # ── 8. Commit updated state ────────────────────────────────────
        self.reads_ok += 1
        with self._lock:
            self._timer_raw    = timer_raw
            self._progress_raw = progress
            self._rpm          = rpm
            self._gear         = gear
            self._velocity_raw = velocity_raw
            self._steering_raw = steering_raw
            self._visual_timer = current_vt
            self._connected    = True
            self._last_ok      = time.time()

        if not self._first_read_logged and self._direct_mode:
            print(
                f"[DataExtractor] First direct read: "
                f"timer={timer_raw}, progress={progress:.4f}, gear={gear}, "
                f"vt={current_vt}, rpm={rpm}, velocity={velocity_raw:.1f}"
            )
            self._first_read_logged = True

        return new_vals
