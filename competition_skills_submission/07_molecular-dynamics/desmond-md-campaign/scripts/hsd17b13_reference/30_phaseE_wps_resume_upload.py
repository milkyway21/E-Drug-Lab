#!/usr/bin/env python3
"""Resume failed PhaseE uploads to WPS cloud until sync is complete.

Watches syncassistant.db / cache.db / precloudfile.db. When the pending queue
stalls or items flip back to failed, re-queue them and nudge wpscloudsvr.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

def _required_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Set {name} before running this helper")
    return Path(value).expanduser()


PROJECT_ROOT = _required_path("EDRUG_MD_PROJECT_ROOT")
BASE = _required_path("EDRUG_WPS_BASE")
PDB = BASE / "precloudfile.db"
CDB = BASE / "cache.db"
SDB = BASE / "syncassistant.db"
LOG = PROJECT_ROOT / "logs/phaseE_wps_resume.log"
LOCAL_PHASEE = PROJECT_ROOT / "05_analysis/phaseE_corrected_pose_2_50_all40_20260727"
STATUS = LOCAL_PHASEE / "WPS_RESUME_STATUS.txt"
CLOUD_PHASEE = _required_path("EDRUG_WPS_PHASEE_DIR")

POLL_S = 30
STALL_ROUNDS = 4  # ~2 min with no progress -> requeue
MAX_HOURS = 12


def log(msg: str) -> None:
    line = f"{datetime.now():%F %T} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def q(db: Path, sql: str, args=()):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def snap() -> dict:
    sync = dict(
        q(
            SDB,
            "SELECT status,count(*) FROM sync_assistant_table "
            "WHERE cloudPath LIKE '%phaseE%' GROUP BY status",
        )
    )
    xfer = dict(q(CDB, "SELECT status,count(*) FROM filetransfer_table GROUP BY status"))
    pre = dict(q(PDB, "SELECT taskStatus,count(*) FROM pre_cloudfile GROUP BY taskStatus"))
    pending = q(
        SDB,
        "SELECT count(*), coalesce(sum(completeSize),0), coalesce(sum(fileSize),0) "
        "FROM sync_assistant_table WHERE cloudPath LIKE '%phaseE%' "
        "AND status IN (0,1,2,3)",
    )[0]
    latest = q(
        SDB,
        "SELECT id,status,fileName,completeSize,fileSize,errorCode "
        "FROM sync_assistant_table ORDER BY id DESC LIMIT 3",
    )
    fails = q(
        SDB,
        "SELECT count(*) FROM sync_assistant_table "
        "WHERE cloudPath LIKE '%phaseE%' AND status=5",
    )[0][0]
    ok = sync.get(4, 0)
    return {
        "sync": sync,
        "xfer": xfer,
        "pre": pre,
        "pending_n": pending[0],
        "pending_done": pending[1],
        "pending_total": pending[2],
        "latest": latest,
        "fails": fails,
        "ok": ok,
    }


def write_status(s: dict, note: str = "") -> None:
    pct = 0.0
    if s["pending_total"]:
        pct = 100.0 * s["pending_done"] / s["pending_total"]
    text = (
        f"time={datetime.now().isoformat()}\n"
        f"note={note}\n"
        f"phaseE_sync_ok={s['ok']}\n"
        f"phaseE_sync_fail={s['fails']}\n"
        f"phaseE_sync_by_status={s['sync']}\n"
        f"pending_n={s['pending_n']} pending_bytes={s['pending_done']}/{s['pending_total']} ({pct:.1f}%)\n"
        f"pre_cloudfile={s['pre']}\n"
        f"filetransfer={s['xfer']}\n"
        f"latest={s['latest']}\n"
    )
    STATUS.write_text(text)


def ensure_cloudsvr() -> None:
    out = subprocess.getoutput("pgrep -a wpscloudsvr || true")
    if "FileTransfer" in out or "wpscloudsvr" in out:
        return
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":1")
    env.setdefault("XAUTHORITY", "/run/user/1000/gdm/Xauthority")
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus")
    env.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")
    log("restarting wpscloudsvr FileTransfer")
    subprocess.Popen(
        [
            "/opt/kingsoft/wps-office/office6/wpscloudsvr",
            "/qingbangong",
            "/wpsbox",
            "/tab:FileTransfer",
            "/category:filetransfer",
            "/trayState:correct",
            "/from:kstartpage",
            "autologin",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )


def requeue_failed() -> dict:
    """Re-queue failed PhaseE tasks. Returns counts."""
    counts = {}
    # pre_cloudfile 5 -> 0 if staging exists
    con = sqlite3.connect(PDB)
    rows = con.execute(
        "SELECT dbId, localPath FROM pre_cloudfile WHERE taskStatus=5"
    ).fetchall()
    n = 0
    for db_id, lp in rows:
        if lp and Path(lp).is_file():
            con.execute("UPDATE pre_cloudfile SET taskStatus=0 WHERE dbId=?", (db_id,))
            n += 1
    con.commit()
    con.close()
    counts["pre"] = n

    con = sqlite3.connect(CDB)
    cur = con.execute(
        """
        UPDATE filecache_data
        SET uploadCode=0, abandoned=0, isCurrentSyncTask=1
        WHERE uploadCode != 0 AND (syncFileFolder LIKE '%phaseE%' OR vPath LIKE '%phaseE%')
        """
    )
    counts["filecache"] = cur.rowcount
    cur = con.execute(
        """
        UPDATE file_metadata_table
        SET fileState=0
        WHERE fileState=16 AND taskId IN (
          SELECT taskId FROM filecache_data
          WHERE syncFileFolder LIKE '%phaseE%' OR vPath LIKE '%phaseE%'
        )
        """
    )
    counts["metadata"] = cur.rowcount
    cur = con.execute(
        """
        UPDATE filetransfer_table
        SET status=1, errorCode=0, errorMsg='', completeSize=0
        WHERE status=5 AND (cloudPath LIKE '%phaseE%' OR localPath LIKE '%phaseE%')
        """
    )
    counts["xfer"] = cur.rowcount
    con.commit()
    con.close()

    con = sqlite3.connect(SDB)
    cur = con.execute(
        """
        UPDATE sync_assistant_table
        SET status=0, errorCode=0, errorMsg='', completeSize=0
        WHERE status=5 AND cloudPath LIKE '%phaseE%'
        """
    )
    counts["sync"] = cur.rowcount
    con.commit()
    con.close()
    return counts


def active_non_phasee_upload(s: dict) -> bool:
    """True if a non-phaseE file is currently uploading (status 3)."""
    for row in s["latest"]:
        # id,status,fileName,...
        if row[1] == 3 and "phaseE" not in str(row).lower():
            # check cloudPath via query
            pass
    rows = q(
        SDB,
        "SELECT fileName, cloudPath, completeSize, fileSize FROM sync_assistant_table "
        "WHERE status=3 ORDER BY id DESC LIMIT 5",
    )
    for name, cpath, done, total in rows:
        if cpath and "phaseE" not in cpath:
            return True
        if name and "phaseE" not in name and (cpath is None or "phaseE" not in cpath):
            # monitor.xlsx etc.
            if name != "phaseE_corrected_pose_2_50_all40_20260727":
                return True
    return False


def main() -> int:
    log("phaseE WPS resume watchdog start")
    ensure_cloudsvr()
    s0 = snap()
    write_status(s0, "start")
    log(f"initial ok={s0['ok']} fail={s0['fails']} pending={s0['pending_n']} sync={s0['sync']}")

    # Initial requeue if there are fails and nothing pending
    if s0["fails"] and s0["pending_n"] == 0:
        c = requeue_failed()
        log(f"initial requeue {c}")
        ensure_cloudsvr()

    start = time.time()
    last_done = -1
    stall = 0
    rounds = 0

    while time.time() - start < MAX_HOURS * 3600:
        time.sleep(POLL_S)
        rounds += 1
        ensure_cloudsvr()
        s = snap()
        write_status(s, f"round={rounds} stall={stall}")
        log(
            f"ok={s['ok']} fail={s['fails']} pending={s['pending_n']} "
            f"bytes={s['pending_done']}/{s['pending_total']} sync={s['sync']} "
            f"latest={s['latest'][:2]}"
        )

        # Success criteria: no pending, no fails for phaseE
        if s["pending_n"] == 0 and s["fails"] == 0:
            # double-check uploadCode
            bad = q(
                CDB,
                "SELECT count(*) FROM filecache_data WHERE uploadCode!=0 AND "
                "(syncFileFolder LIKE '%phaseE%' OR vPath LIKE '%phaseE%')",
            )[0][0]
            if bad == 0:
                log("COMPLETE: no pending/failed phaseE uploads")
                write_status(s, "COMPLETE")
                return 0
            else:
                log(f"pending clear but filecache bad={bad}; requeue")
                log(f"requeue {requeue_failed()}")

        # Progress?
        marker = (s["ok"], s["pending_done"], s["fails"], s["pending_n"])
        if s["pending_done"] != last_done or s["ok"] != getattr(main, "_last_ok", -1):
            stall = 0
            last_done = s["pending_done"]
            main._last_ok = s["ok"]
        else:
            stall += 1

        # If only non-phaseE busy, wait
        if active_non_phasee_upload(s) and s["pending_n"] > 0:
            stall = min(stall, STALL_ROUNDS - 1)  # don't requeue while other upload runs
            continue

        if stall >= STALL_ROUNDS and (s["fails"] > 0 or s["pending_n"] > 0):
            # If pending stuck at 0 bytes forever, requeue fails / nudge
            c = requeue_failed()
            log(f"stall requeue after {stall} rounds: {c}")
            # Soft restart cloudsvr
            subprocess.call(["pkill", "-f", "wpscloudsvr .*FileTransfer"])
            time.sleep(2)
            ensure_cloudsvr()
            stall = 0

    log("TIMEOUT")
    write_status(snap(), "TIMEOUT")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
