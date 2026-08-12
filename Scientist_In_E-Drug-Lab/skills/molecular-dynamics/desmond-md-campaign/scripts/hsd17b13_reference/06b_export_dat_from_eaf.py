#!/usr/bin/env python3
"""Export SEA .dat tables from a *-out.eaf when event_analysis report fails."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def _result_array(text: str, start: int) -> list[str]:
    m = re.search(r"Result = \[([^\]]*)\]", text[start : start + 50000])
    if not m:
        return []
    return m.group(1).split()


def _parse_rmsd(text: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for m in re.finditer(r"\{RMSD = \{", text):
        chunk = text[m.start() : m.start() + 800]
        asl_m = re.search(r'ASL = "([^"]+)"', chunk)
        fit_m = re.search(r'FitBy\s*=\s*"?([^"\n]+)"?', chunk)
        vals = [float(x) for x in _result_array(text, m.start())]
        if not asl_m or not vals:
            continue
        asl = asl_m.group(1)
        if "atom.ptype ' CA '" in asl:
            out["ca"] = vals
        elif "sidechain" in asl:
            out["side"] = vals
        elif "backbone" in asl:
            out["bb"] = vals
        elif "protein and not (atom.ele H)" in asl:
            out["heavy"] = vals
        elif "res.ptype UNK" in asl:
            if fit_m and "protein" in fit_m.group(1):
                out["lig_p"] = vals
            else:
                out["lig_l"] = vals
    return out


def _write_pl_rmsd(path: Path, rmsd: dict[str, list[float]]) -> None:
    n = len(rmsd["ca"])
    lines = [
        "  # frame#    Prot_CA   Prot_Backbone  Prot_Sidechain  "
        "Prot_All_Heavy Lig_wrt_Protein  Lig_wrt_Ligand"
    ]
    for i in range(n):
        lines.append(
            f"{i:10d} {rmsd['ca'][i]:10.3f} {rmsd['bb'][i]:15.3f} "
            f"{rmsd['side'][i]:15.3f} {rmsd['heavy'][i]:15.3f} "
            f"{rmsd['lig_p'][i]:15.3f} {rmsd['lig_l'][i]:15.3f}"
        )
    path.write_text("\n".join(lines) + "\n")


def _nested_frames(blob: str) -> list[list[list[str]]]:
    """Parse HBondResult-like nested lists of string tokens."""
    # Keep only frame-level lists after outer [
    # Strategy: find each `[[frame ...` or `[]`
    frames: list[list[list[str]]] = []
    # Remove newlines for simpler scanning inside Result arrays
    # But keep structure with regex for contact entries
    entries = re.findall(
        r"\[(\d+)\s+\"([^\"]+)\"\s+([^\s\]]+)\s+\"([^\"]+)\"(?:\s+([^\s\]]+))?.*?\]",
        blob,
        flags=re.S,
    )
    # Above may miss Hydrophobic which has fewer fields.
    return entries  # type: ignore[return-value]


def _export_contacts(text: str, data_dir: Path) -> None:
    # Capture each Result array for contact types
    mapping = {
        "HBondResult": ("PL-Contacts_HBond.dat", "hbond"),
        "HydrophobicResult": ("PL-Contacts_Hydrophobic.dat", "hydrophobic"),
        "PiPiResult": ("PL-Contacts_Pi-Pi.dat", "pipi"),
        "PiCatResult": ("PL-Contacts_Pi-Cation.dat", "picat"),
        "PolarResult": ("PL-Contacts_Ionic.dat", "ionic"),
        "MetalResult": ("PL-Contacts_Metal.dat", "metal"),
        "WaterBridgeResult": ("PL-Contacts_WaterBridge.dat", "water"),
    }
    for key, (filename, kind) in mapping.items():
        m = re.search(rf"{key} = (\[.*?\n\s*\])", text, flags=re.S)
        blob = m.group(1) if m else "[]"
        path = data_dir / filename
        if kind == "hbond" or kind == "water":
            header = (
                "  # Frame#   Residue#      Chain    ResName   AtomName  "
                "LigandFragment  LigandAtomName \n"
            )
            rows = re.findall(
                r"\[(\d+)\s+\"([A-Za-z0-9]+):([A-Za-z0-9]+)_(\d+):([^\"]+)\"\s+"
                r"[^\s\]]+\s+\"([^\"]+):([^\"]+)\"",
                blob,
            )
            lines = [header]
            for frame, chain, resn, resi, atom, frag, latom in rows:
                lines.append(
                    f"{int(frame):10d} {int(resi):10d} {chain:>10s} {resn:>10s} "
                    f"{atom:>10s} {frag:>15s} {latom:>15s} \n"
                )
            path.write_text("".join(lines))
        elif kind == "hydrophobic":
            header = (
                "  # Frame#   Residue#      Chain    ResName  LigandFragment \n"
            )
            rows = re.findall(
                r"\[(\d+)\s+\"([A-Za-z0-9]+):([A-Za-z0-9]+)_(\d+)\"\s+\"([^\"]+)\"",
                blob,
            )
            lines = [header]
            for frame, chain, resn, resi, frag in rows:
                lines.append(
                    f"{int(frame):10d} {int(resi):10d} {chain:>10s} "
                    f"{resn:>10s} {frag:>15s} \n"
                )
            path.write_text("".join(lines))
        elif kind == "pipi":
            header = (
                "  # Frame#   Residue#      Chain    ResName  LigandFragment"
                "        Distance       Type\n"
            )
            rows = re.findall(
                r"\[(\d+)\s+\"([A-Za-z0-9]+):([A-Za-z0-9]+)_(\d+)\"\s+\"([^\"]+)\""
                r".*?([0-9]+\.[0-9]+).*?\"([^\"]+)\"",
                blob,
            )
            lines = [header]
            for frame, chain, resn, resi, frag, dist, typ in rows:
                lines.append(
                    f"{int(frame):10d} {int(resi):10d} {chain:>10s} {resn:>10s} "
                    f"{frag:>15s} {float(dist):15.3f} {typ:>10s}\n"
                )
            path.write_text("".join(lines))
        elif kind == "picat":
            header = (
                "  # Frame#   Residue#      Chain    ResName  LigandFragment"
                "        Distance\n"
            )
            rows = re.findall(
                r"\[(\d+)\s+\"([A-Za-z0-9]+):([A-Za-z0-9]+)_(\d+)\"\s+\"([^\"]+)\""
                r".*?([0-9]+\.[0-9]+)",
                blob,
            )
            lines = [header]
            for frame, chain, resn, resi, frag, dist in rows:
                lines.append(
                    f"{int(frame):10d} {int(resi):10d} {chain:>10s} {resn:>10s} "
                    f"{frag:>15s} {float(dist):15.3f}\n"
                )
            path.write_text("".join(lines))
        elif kind == "ionic":
            header = (
                "  # Frame#   Residue#      Chain    ResName   AtomName  "
                "LigandFragment      LigandAtom   Distance\n"
            )
            rows = re.findall(
                r"\[(\d+)\s+\"([A-Za-z0-9]+):([A-Za-z0-9]+)_(\d+):([^\"]+)\"\s+"
                r"[^\s\]]+\s+\"([^\"]+):([^\"]+)\".*?([0-9]+\.[0-9]+)",
                blob,
            )
            lines = [header]
            for frame, chain, resn, resi, atom, frag, latom, dist in rows:
                lines.append(
                    f"{int(frame):10d} {int(resi):10d} {chain:>10s} {resn:>10s} "
                    f"{atom:>10s} {frag:>15s} {latom:>15s} {float(dist):10.3f} \n"
                )
            path.write_text("".join(lines))
        else:  # metal
            header = (
                "  # Frame#            Type            Site       MetalSite"
                "   Distance\n"
            )
            path.write_text(header)


def _export_rmsf_and_props(text: str, data_dir: Path, n_frames: int) -> None:
    # Protein RMSF: multiple ASL blocks
    ca = bb = side = heavy = None
    for m in re.finditer(r"\{RMSF = \{", text):
        chunk = text[m.start() : m.start() + 600]
        asl_m = re.search(r'ASL = "([^"]+)"', chunk)
        vals = [float(x) for x in _result_array(text, m.start())]
        if not asl_m:
            continue
        asl = asl_m.group(1)
        if "atom.ptype ' CA '" in asl:
            ca = vals
        elif "sidechain" in asl:
            side = vals
        elif "backbone" in asl:
            bb = vals
        elif "protein and not (atom.ele H)" in asl:
            heavy = vals
        elif "res.ptype UNK" in asl:
            # ligand rmsf wrt ligand or protein distinguished by FitBy
            fit_m = re.search(r'FitBy\s*=\s*"?([^"\n]+)"?', chunk)
            path = data_dir / "L_RMSF.dat"
            if not path.exists() or (fit_m and "protein" in fit_m.group(1)):
                # write later with both series
                pass

    # Build minimal P_RMSF with residue index only (names unknown → UNK_#)
    if ca and bb and side and heavy:
        n_res = len(ca)
        lines = [
            "# Residue#      Chain    ResName LigandContact         CA   "
            "Backbone  Sidechain  All_Heavy   B-factor"
        ]
        for i in range(n_res):
            lines.append(
                f"{i:10d} {'A':>10s} {'UNK_'+str(i+1):>10s} {'No':>11s} "
                f"{ca[i]:10.3f} {bb[i]:10.3f} {side[i]:10.3f} "
                f"{heavy[i]:10.3f} {0.0:10.3f}"
            )
        (data_dir / "P_RMSF.dat").write_text("\n".join(lines) + "\n")

    # Ligand RMSF: collect both FitBy variants
    lig_p = lig_l = None
    for m in re.finditer(r"\{RMSF = \{", text):
        chunk = text[m.start() : m.start() + 600]
        asl_m = re.search(r'ASL = "([^"]+)"', chunk)
        if not asl_m or "res.ptype UNK" not in asl_m.group(1):
            continue
        vals = [float(x) for x in _result_array(text, m.start())]
        fit_m = re.search(r'FitBy\s*=\s*"?([^"\n]+)"?', chunk)
        if fit_m and "protein" in fit_m.group(1):
            lig_p = vals
        else:
            lig_l = vals
    if lig_l is None and lig_p is not None:
        lig_l = lig_p
    if lig_p is None and lig_l is not None:
        lig_p = lig_l
    if lig_p and lig_l:
        lines = ["   # Atom# PDBResName  wrt_Protein   wrt_Ligand "]
        for i, (a, b) in enumerate(zip(lig_p, lig_l), start=1):
            lines.append(f"{i:10d} {'':>10s} {a:12.3f} {b:12.3f}")
        (data_dir / "L_RMSF.dat").write_text("\n".join(lines) + "\n")

    # Ligand properties from named series
    def series(name: str) -> list[float]:
        m = re.search(
            rf"\{{{name} = \{{.*?Result = \[([^\]]*)\]",
            text,
            flags=re.S,
        )
        if not m:
            return [0.0] * n_frames
        return [float(x) for x in m.group(1).split()]

    rgyr = series("Rad_Gyration")
    molsa = series("Molecular_Surface_Area")
    sasa = series("SA_Surface_Area")
    psa = series("Polar_Surface_Area")
    # RMSD column in L-Properties is ligand-internal style; reuse lig_l if present
    lig_rmsd = lig_l if lig_l is not None else [0.0] * n_frames
    n = min(len(rgyr), len(molsa), len(sasa), len(psa), len(lig_rmsd), n_frames)
    lines = [
        "  Frame #         RMSD         rGyr      intraHB        MolSA"
        "         SASA          PSA"
    ]
    for i in range(n):
        lines.append(
            f"{i:9d} {lig_rmsd[i]:12.3f} {rgyr[i]:12.3f} {0:12d} "
            f"{molsa[i]:12.3f} {sasa[i]:12.3f} {psa[i]:12.3f}"
        )
    (data_dir / "L-Properties.dat").write_text("\n".join(lines) + "\n")
    # empty torsions placeholder
    (data_dir / "L_Torsions.dat").write_text("# Frame#\n")


def export_one(eaf: Path, data_dir: Path) -> None:
    text = eaf.read_text(errors="ignore")
    data_dir.mkdir(parents=True, exist_ok=True)
    rmsd = _parse_rmsd(text)
    required = ["ca", "bb", "side", "heavy", "lig_p", "lig_l"]
    missing = [k for k in required if k not in rmsd]
    if missing:
        raise RuntimeError(f"{eaf}: missing RMSD series {missing}")
    _write_pl_rmsd(data_dir / "PL_RMSD.dat", rmsd)
    _export_contacts(text, data_dir)
    _export_rmsf_and_props(text, data_dir, len(rmsd["ca"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="+", required=True)
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    ap.add_argument("--analysis-root", type=Path, default=None)
    ap.add_argument("--eaf-pattern", default="{mid}_sea-out.eaf")
    args = ap.parse_args()
    analysis_root = args.analysis_root or args.root / "05_analysis/per_molecule"
    for mid in args.ids:
        out = analysis_root / mid
        eaf = out / args.eaf_pattern.format(mid=mid)
        data = out / "data"
        export_one(eaf, data)
        if args.analysis_root is None:
            inter = args.root / "05_analysis/interaction_tables" / mid
            inter.mkdir(parents=True, exist_ok=True)
            for f in data.glob("*.dat"):
                dest = inter / f.name
                dest.write_bytes(f.read_bytes())
        (out / "SEA_DONE.flag").write_text("eaf_export\n")
        print(f"{mid}: exported from eaf -> {data}")


if __name__ == "__main__":
    main()
