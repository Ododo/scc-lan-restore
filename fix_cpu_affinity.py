"""
Mitigation for the coop "out of sync" errors (https://github.com/Ododo/scc-lan-restore/issues/3)

Community testing in issue #3 showed that desyncs largely disappear when both
machines run the game with SMT (Hyper-Threading) and Intel E-cores disabled in
the BIOS, i.e. when the game only ever runs on one hardware thread per physical
performance core. The coop protocol replays inputs on both machines and relies
on both sides keeping a fixed frame pace, so game threads bouncing between SMT
siblings or efficiency cores plausibly causes the timing divergence that trips
the game's divergence check.

This module reproduces that setup in software so players don't have to touch
their BIOS: it watches for the game process and pins it to the first hardware
thread of each physical performance core.

Can be disabled by running scc_lan_helper.py with --no-affinity-fix.
"""

import sys
import time

from log import logger_zh, logger_en

# The game executable is conviction_game.exe, match by prefix to also catch
# renamed/launcher variants (and the 15-char truncated comm value on Linux).
GAME_PROCESS_PREFIX = "conviction"
POLL_INTERVAL = 5


if sys.platform.startswith("win"):
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _GROUP_AFFINITY(ctypes.Structure):
        _fields_ = [
            ("Mask", ctypes.c_size_t),
            ("Group", wintypes.WORD),
            ("Reserved", wintypes.WORD * 3),
        ]

    class _PROCESSOR_RELATIONSHIP(ctypes.Structure):
        _fields_ = [
            ("Flags", ctypes.c_ubyte),
            ("EfficiencyClass", ctypes.c_ubyte),
            ("Reserved", ctypes.c_ubyte * 20),
            ("GroupCount", wintypes.WORD),
            ("GroupMask", _GROUP_AFFINITY * 1),
        ]

    class _PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    _kernel32.GetLogicalProcessorInformationEx.argtypes = [
        ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)
    ]
    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    _kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.GetProcessAffinityMask.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p
    ]
    _kernel32.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    _RELATION_PROCESSOR_CORE = 0
    _ERROR_INSUFFICIENT_BUFFER = 122
    _TH32CS_SNAPPROCESS = 0x2
    _INVALID_HANDLE_VALUE = ctypes.c_size_t(-1).value
    _PROCESS_QUERY_INFORMATION = 0x0400
    _PROCESS_SET_INFORMATION = 0x0200

    def _target_cpus():
        # Enumerate physical cores; each entry carries the mask of its SMT
        # threads and its EfficiencyClass (on hybrid CPUs, P-cores have the
        # highest class; on non-hybrid CPUs all cores share one class).
        length = wintypes.DWORD(0)
        _kernel32.GetLogicalProcessorInformationEx(
            _RELATION_PROCESSOR_CORE, None, ctypes.byref(length)
        )
        if ctypes.get_last_error() != _ERROR_INSUFFICIENT_BUFFER:
            return set()
        buf = (ctypes.c_ubyte * length.value)()
        if not _kernel32.GetLogicalProcessorInformationEx(
            _RELATION_PROCESSOR_CORE, buf, ctypes.byref(length)
        ):
            return set()

        cores = []
        offset = 0
        while offset + 8 <= length.value:
            relationship = int.from_bytes(bytes(buf[offset:offset + 4]), "little")
            size = int.from_bytes(bytes(buf[offset + 4:offset + 8]), "little")
            if size <= 0:
                break
            if relationship == _RELATION_PROCESSOR_CORE:
                rel = _PROCESSOR_RELATIONSHIP.from_buffer(buf, offset + 8)
                group_offset = offset + 8 + _PROCESSOR_RELATIONSHIP.GroupMask.offset
                for i in range(rel.GroupCount):
                    group = _GROUP_AFFINITY.from_buffer(
                        buf, group_offset + i * ctypes.sizeof(_GROUP_AFFINITY)
                    )
                    # SetProcessAffinityMask only addresses processor group 0,
                    # which covers up to 64 logical CPUs (plenty here).
                    if group.Group == 0 and group.Mask:
                        cores.append((rel.EfficiencyClass, group.Mask))
            offset += size

        if not cores:
            return set()
        best_class = max(eff for eff, _ in cores)
        cpus = set()
        for eff, core_mask in cores:
            if eff == best_class:
                # keep only the first SMT thread of the core
                first_thread = core_mask & -core_mask
                cpus.add(first_thread.bit_length() - 1)
        return cpus

    def _find_game_pids():
        pids = []
        snapshot = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if not snapshot or snapshot == _INVALID_HANDLE_VALUE:
            return pids
        try:
            entry = _PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
            found = _kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while found:
                if entry.szExeFile.lower().startswith(GAME_PROCESS_PREFIX):
                    pids.append(entry.th32ProcessID)
                found = _kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            _kernel32.CloseHandle(snapshot)
        return pids

    def _apply_affinity(pid, cpus):
        # returns True if changed, False if already pinned, None on failure
        mask = 0
        for cpu in cpus:
            mask |= 1 << cpu
        handle = _kernel32.OpenProcess(
            _PROCESS_QUERY_INFORMATION | _PROCESS_SET_INFORMATION, False, pid
        )
        if not handle:
            return None
        try:
            process_mask = ctypes.c_size_t()
            system_mask = ctypes.c_size_t()
            if not _kernel32.GetProcessAffinityMask(
                handle, ctypes.byref(process_mask), ctypes.byref(system_mask)
            ):
                return None
            if process_mask.value == mask:
                return False
            if not _kernel32.SetProcessAffinityMask(handle, mask):
                return None
            return True
        finally:
            _kernel32.CloseHandle(handle)

else:
    import glob
    import os

    def _first_cpu(cpu_list):
        # sysfs cpu lists look like "0-1" or "0,4"
        return int(cpu_list.split(",")[0].split("-")[0])

    def _target_cpus():
        # One CPU per physical core (first SMT sibling). Linux exposes no
        # portable P/E-core distinction, so no efficiency filtering here.
        cpus = set()
        for path in glob.glob(
            "/sys/devices/system/cpu/cpu[0-9]*/topology/thread_siblings_list"
        ):
            try:
                with open(path) as f:
                    cpus.add(_first_cpu(f.read().strip()))
            except (OSError, ValueError):
                continue
        return cpus

    def _find_game_pids():
        pids = []
        for comm_path in glob.glob("/proc/[0-9]*/comm"):
            try:
                with open(comm_path) as f:
                    name = f.read().strip().lower()
            except OSError:
                continue
            if name.startswith(GAME_PROCESS_PREFIX):
                pids.append(int(comm_path.split("/")[2]))
        return pids

    def _apply_affinity(pid, cpus):
        try:
            if os.sched_getaffinity(pid) == cpus:
                return False
            os.sched_setaffinity(pid, cpus)
            return True
        except OSError:
            return None


def affinity_hook():
    cpus = _target_cpus()
    if len(cpus) < 2:
        logger_zh.info("防不同步补丁：无法获取 CPU 拓扑信息（或可用核心过少），跳过绑定 CPU 核心\n")
        logger_en.info(
            "Out-of-sync mitigation: could not read CPU topology (or too few cores), skipping CPU pinning\n"
        )
        return

    cpu_list = ",".join(str(cpu) for cpu in sorted(cpus))
    logger_zh.info(
        f"防不同步补丁：检测到游戏后，会将游戏绑定到每个物理性能核心的第一个线程 (CPU: {cpu_list})，"
        "以缓解联机不同步问题 (issue #3)。添加 --no-affinity-fix 参数可禁用此功能\n"
    )
    logger_en.info(
        f"Out-of-sync mitigation: once the game is detected it will be pinned to the first thread "
        f"of each physical performance core (CPUs: {cpu_list}) to mitigate coop desyncs (issue #3). "
        "Run with --no-affinity-fix to disable\n"
    )

    pinned = set()
    while True:
        pids = set(_find_game_pids())
        pinned &= pids  # forget processes that exited
        for pid in pids:
            changed = _apply_affinity(pid, cpus)
            if changed is None:
                if pid not in pinned:
                    logger_zh.info(f"防不同步补丁：无法设置游戏进程 (pid {pid}) 的 CPU 亲和性\n")
                    logger_en.info(
                        f"Out-of-sync mitigation: failed to set CPU affinity of game process (pid {pid})\n"
                    )
                    pinned.add(pid)  # don't spam the log every poll
            elif changed and pid not in pinned:
                logger_zh.info(
                    f"检测到游戏进程 (pid {pid})，已将其绑定到物理性能核心 (CPU: {cpu_list})\n"
                )
                logger_en.info(
                    f"Game process detected (pid {pid}), pinned it to physical performance cores (CPUs: {cpu_list})\n"
                )
                pinned.add(pid)
            else:
                pinned.add(pid)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    affinity_hook()
