"""
Bin down TauREx-format xsec HDF5 files (.xsec.TauREx.h5) from their native
resolution (R15000) to a coarser resolution (default R100), for use during
agent testing/development where full spectral accuracy is not needed.

Format of a TauREx xsec.h5 file (as produced by ExoMol / used by TauREx's
OpacityCache):
    DOI          (1,)              object   - citation DOI
    key_iso_ll   (1,)              object   - ExoMol line-list identifier
    mol_name     (1,)              object   - molecule name (e.g. b'H2O')
    p            (n_pressure,)     float64  - pressure grid (bar)
    t            (n_temperature,)  float64  - temperature grid (K)
    bin_edges    (n_wavenumber,)   float64  - wavenumber grid points (cm^-1).
                                               NOT N+1 edges despite the name;
                                               one value per xsecarr point.
                                               Adjacent ratio is constant:
                                               bin_edges[i+1]/bin_edges[i] = 1 + 1/R
    xsecarr      (n_p, n_t, n_wavenumber) float64 - cross sections (cm^2/molecule)

Binning-down approach: build a new wavenumber grid with the same start/end
range but a coarser constant-R spacing (ratio = 1 + 1/R_new), then average
all xsecarr points whose original wavenumber falls within each new grid
"bin" (defined by the midpoints, in log-space, to its neighboring new grid
points).
"""
import argparse
from pathlib import Path

import h5py
import numpy as np


def make_coarse_grid(wn_min: float, wn_max: float, r_new: int) -> np.ndarray:
    """Build a constant-R geometric wavenumber grid covering [wn_min, wn_max]."""
    ratio = 1.0 + 1.0 / r_new
    n_points = int(np.ceil(np.log(wn_max / wn_min) / np.log(ratio))) + 1
    grid = wn_min * ratio ** np.arange(n_points)
    # Make sure we cover the original max (append if needed)
    if grid[-1] < wn_max:
        grid = np.append(grid, wn_max)
    return grid


def bin_down_file(src_path: Path, dst_path: Path, r_new: int = 100) -> None:
    with h5py.File(src_path, "r") as fsrc:
        bin_edges = fsrc["bin_edges"][:]
        xsecarr = fsrc["xsecarr"][:]  # (n_p, n_t, n_wn)
        p = fsrc["p"][:]
        t = fsrc["t"][:]
        mol_name = fsrc["mol_name"][:]
        key_iso_ll = fsrc["key_iso_ll"][:]
        doi = fsrc["DOI"][:]
        # HDF5Opacity._load_hdf_file() requires p.attrs["units"] (and reads
        # units off the other datasets too), so we must preserve these.
        attrs_by_name = {
            name: dict(fsrc[name].attrs)
            for name in ("DOI", "key_iso_ll", "mol_name", "p", "t", "bin_edges", "xsecarr")
        }

    n_p, n_t, n_wn_orig = xsecarr.shape
    assert n_wn_orig == len(bin_edges)

    new_grid = make_coarse_grid(bin_edges[0], bin_edges[-1], r_new)
    n_wn_new = len(new_grid)

    # Bin boundaries in log-space (midpoints between neighboring new grid points)
    log_grid = np.log(new_grid)
    log_mid = (log_grid[1:] + log_grid[:-1]) / 2.0
    # Assign each original point to a new-grid bin index (0..n_wn_new-1)
    bin_idx = np.searchsorted(log_mid, np.log(bin_edges))
    bin_idx = np.clip(bin_idx, 0, n_wn_new - 1)

    # bin_idx is monotonically non-decreasing (both grids sorted increasing),
    # so we can use reduceat for a fast grouped mean over the last axis.
    flat = xsecarr.reshape(n_p * n_t, n_wn_orig)
    # Start index of each group within the sorted bin_idx array
    change_points = np.flatnonzero(np.diff(bin_idx)) + 1
    group_starts = np.concatenate(([0], change_points))
    group_ids = bin_idx[group_starts]  # which new bin each group corresponds to

    sums = np.add.reduceat(flat, group_starts, axis=1)
    counts = np.diff(np.append(group_starts, n_wn_orig))
    means = sums / counts[None, :]

    # Scatter into a full-length (n_wn_new) array (some new bins may have
    # received no original points if r_new > original resolution; shouldn't
    # happen here since r_new << 15000, but guard anyway by forward-filling).
    out = np.full((n_p * n_t, n_wn_new), np.nan)
    out[:, group_ids] = means
    # Forward-fill any empty bins (shouldn't occur in practice)
    if np.isnan(out).any():
        for row in out:
            mask = np.isnan(row)
            if mask.any():
                idx = np.where(~mask, np.arange(len(row)), 0)
                np.maximum.accumulate(idx, out=idx)
                row[mask] = row[idx[mask]]

    new_xsecarr = out.reshape(n_p, n_t, n_wn_new)

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(dst_path, "w") as fdst:
        datasets = {
            "DOI": doi,
            "key_iso_ll": key_iso_ll,
            "mol_name": mol_name,
            "p": p,
            "t": t,
            "bin_edges": new_grid,
            "xsecarr": new_xsecarr,
        }
        for name, data in datasets.items():
            ds = fdst.create_dataset(name, data=data)
            for attr_key, attr_val in attrs_by_name[name].items():
                ds.attrs[attr_key] = attr_val

    orig_mb = src_path.stat().st_size / 1e6
    new_mb = dst_path.stat().st_size / 1e6
    print(f"{src_path.name}: {n_wn_orig} -> {n_wn_new} points, "
          f"{orig_mb:.1f}MB -> {new_mb:.2f}MB")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src-dir", default="workspace/linelists/xsec")
    parser.add_argument("--dst-dir", default="workspace/linelists/xsec_R100")
    parser.add_argument("--r-new", type=int, default=100)
    parser.add_argument("--only", default=None, help="Substring filter to process a single file (for testing)")
    args = parser.parse_args()

    src_dir = Path(args.src_dir)
    dst_dir = Path(args.dst_dir)

    files = sorted(src_dir.glob("*.xsec.TauREx.h5"))
    if args.only:
        files = [f for f in files if args.only in f.name]

    for src in files:
        dst_name = src.name.replace("R15000", f"R{args.r_new}")
        dst = dst_dir / dst_name
        bin_down_file(src, dst, r_new=args.r_new)


if __name__ == "__main__":
    main()
