"""Wavelength-domain features for rail corrugation.

Corrugation is a spatial pattern on the rail head with a pitch of a few cm to
tens of cm. Its vibration frequency therefore scales with train speed:
f = v / lambda. Converting each recording's spectrum to the wavelength domain
using the speed measured from the 90-tooth pulse makes the same corrugation
pitch land in the same feature at any speed, which frequency bands cannot do.

These features are added on top of the ported baseline features; the
experiment in scripts/rail_wavelength_experiment.py decides, on the original
grouped folds, whether they earn their place.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import SAMPLE_RATE_HZ, _SENSOR_RE, clean_data

TEETH, WHEEL_DIAMETER_M = 90, 0.85
#: wavelength bands in metres (2 cm .. 1.6 m), short-pitch corrugation first
BANDS_M = ((0.02, 0.05), (0.05, 0.10), (0.10, 0.20), (0.20, 0.40), (0.40, 0.80), (0.80, 1.60))


def speed_m_s(pulses: np.ndarray) -> float:
    transitions = int(np.count_nonzero(np.diff(pulses) != 0))
    seconds = len(pulses) / SAMPLE_RATE_HZ
    return transitions / (2 * TEETH) / seconds * np.pi * WHEEL_DIAMETER_M


def wavelength_features(frame: pd.DataFrame, data: np.ndarray | None = None) -> dict[str, float]:
    """One row of speed-normalised spectral features, per side and as contrasts."""
    if data is None:
        data = clean_data(frame)
    v = speed_m_s(data[:, 0])
    out: dict[str, float] = {"wl_speed_m_s": float(v)}
    freqs = np.fft.rfftfreq(len(data), d=1.0 / SAMPLE_RATE_HZ)
    side_idx = {"side_i": [], "side_ii": []}
    for idx, col in enumerate(frame.columns[1:], start=1):
        m = _SENSOR_RE.match(col)
        if m and m.group(1) == "Vibration":
            side_idx["side_i" if int(m.group(2)) % 2 else "side_ii"].append(idx)
    valid = freqs > 0
    lam = np.full_like(freqs, np.nan)
    if v > 0:
        lam[valid] = v / freqs[valid]
    for side, idxs in side_idx.items():
        sig = data[:, idxs].astype(np.float64)
        sig -= sig.mean(axis=0, keepdims=True)
        p = np.abs(np.fft.rfft(sig, axis=0)) ** 2            # (freq, channels)
        p_mean = p.mean(axis=1)
        total = max(float(p_mean[valid].sum()), 1e-12)
        for lo, hi in BANDS_M:
            sel = valid & (lam >= lo) & (lam < hi) if v > 0 else np.zeros_like(valid)
            band = p[sel].sum(axis=0) / total if sel.any() else np.zeros(p.shape[1])
            tag = f"{side}_wl_{int(lo * 100)}_{int(hi * 100)}cm"
            out[f"{tag}_mean"] = float(band.mean())
            out[f"{tag}_max"] = float(band.max())
            out[f"{tag}_std"] = float(band.std())
        if v > 0:
            band_sel = valid & (lam >= 0.02) & (lam < 1.6)
            peak = int(np.argmax(np.where(band_sel, p_mean, -1)))
            out[f"{side}_wl_peak_cm"] = float(lam[peak] * 100) if band_sel.any() else 0.0
            out[f"{side}_wl_peak_share"] = float(p_mean[peak] / total) if band_sel.any() else 0.0
            # coherence across axle boxes: corrugation excites every box on the side alike
            ch_share = p[band_sel] / np.maximum(p[band_sel].sum(axis=0, keepdims=True), 1e-12)
            out[f"{side}_wl_peak_coherence"] = float(ch_share[np.argmax(p_mean[band_sel])].mean())
        else:
            out[f"{side}_wl_peak_cm"] = out[f"{side}_wl_peak_share"] = out[f"{side}_wl_peak_coherence"] = 0.0
    for k in [k for k in out if k.startswith("side_i_wl_")]:
        k2 = "side_ii_wl_" + k[len("side_i_wl_"):]
        out["side_contrast_wl_" + k[len("side_i_wl_"):]] = out[k] - out[k2]
    return out
