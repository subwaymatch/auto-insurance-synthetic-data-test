"""Driver names: realistic for the place, and with nothing else attached to them.

Each household is given a synthetic race and ethnicity group, drawn from its ZIP code's Census mix. Surnames are
drawn from the Census 2010 surname table for that group (reference/surnames.csv), and first names, when
reference/first_names.csv is present, from Social Security first-name frequencies for the driver's sex and decade
of birth, reweighted to the group (Tzioumis 2018). Without that file, first names come from reference/names.csv,
independent of group and age.

Married couples usually share a surname, the husband's; how often a wife keeps her own depends on her group
(KEPT_OWN_SURNAME). Children carry the household's surname; other adults their own.

The group is used for nothing else: risk, prices and claims depend on ZIP-level crash and theft data and on the
driver, never on it. It is written only to the instructor answer key (driver_truth.race_ethnicity), so that a
fairness audit, for example estimating race from surname and address with BISG (Bayesian Improved Surname
Geocoding), can be checked against the truth. A name works as a stand-in for race and ethnicity, which is why it
must never be a rating variable.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config as C

GROUPS = ["white", "black", "hispanic", "asian", "other"]
GROUP_LABELS = ["White (non-Hispanic)", "Black (non-Hispanic)", "Hispanic", "Asian or Pacific Islander (non-Hispanic)",
                "Other or multiracial (non-Hispanic)"]
SAME_GROUP_SPOUSE = 0.90        # spouses in the same group (US married couples, Census CPS/ACS: about 10% inter-group)
SAME_GROUP_OTHER_ADULT = 0.85   # other adults in the household (ASSUMED)
# Married women who kept their own surname, by the woman's group, in GROUPS order. Pew Research Center (2023,
# women in opposite-sex marriages): 30% of Hispanic, 10% of White and 9% of Black women kept their name, 14% overall.
# Pew had too few Asian women to report; 25% is ASSUMED, as Korean, Chinese and Vietnamese wives traditionally keep
# their surname. Other or multiracial: the overall 14%. Otherwise a couple shares the husband's surname, as their
# children do; the 5% who hyphenate are not modeled. In a same-sex couple the spouse keeps their name at the same rate.
KEPT_OWN_SURNAME = np.array([0.10, 0.09, 0.30, 0.25, 0.14])


def _cum(w: np.ndarray) -> np.ndarray:
    c = np.cumsum(w, dtype=float)
    return c / c[-1]


@dataclass
class NameSampler:
    surnames: np.ndarray
    surname_cum: list[np.ndarray]                     # per group
    first: dict | None                                # (sex, decade, group) -> (names, cumulative weights)
    fallback_m: np.ndarray
    fallback_f: np.ndarray

    @classmethod
    def load(cls) -> "NameSampler":
        s = pd.read_csv(C.REFERENCE_DIR / "surnames.csv", keep_default_na=False)
        first = None
        path = C.REFERENCE_DIR / "first_names.csv"
        if path.exists():
            f = pd.read_csv(path, keep_default_na=False)
            first = {}
            for (sex, dec), d in f.groupby(["sex", "birth_decade"]):
                for gi, g in enumerate(GROUPS):
                    w = d[g].to_numpy(dtype=float)
                    if w.sum() > 0:
                        first[(sex, int(dec), gi)] = (d.first_name.to_numpy(), _cum(w))
        old = pd.read_csv(C.REFERENCE_DIR / "names.csv", keep_default_na=False)
        return cls(s.surname.to_numpy(), [_cum(s[g].to_numpy(dtype=float)) for g in GROUPS], first,
                   old.name[old.kind == "M"].to_numpy(), old.name[old.kind == "F"].to_numpy())

    @staticmethod
    def zip_mix(zips: pd.DataFrame) -> np.ndarray:
        """Each ZIP's population shares by group (rows sum to 1)."""
        m = zips[["pct_white_nh", "pct_black_nh", "pct_hispanic", "pct_asian_nh"]].to_numpy(dtype=float).clip(0)
        m = np.column_stack([m, (1 - m.sum(axis=1)).clip(0.005)])
        return m / m.sum(axis=1, keepdims=True)

    def draw_group(self, r: np.random.Generator, mix: np.ndarray) -> np.ndarray:
        """One group per row of `mix` (each row a probability vector)."""
        u = r.random(len(mix))[:, None]
        return np.minimum((u > np.cumsum(mix, axis=1)).sum(axis=1), len(GROUPS) - 1)

    def related_group(self, r: np.random.Generator, own: np.ndarray, mix: np.ndarray, p_same: float) -> np.ndarray:
        """A household member's group: the household's with probability p_same, otherwise drawn from the ZIP."""
        return np.where(r.random(len(own)) < p_same, own, self.draw_group(r, mix))

    def surname(self, r: np.random.Generator, group: np.ndarray) -> np.ndarray:
        out = np.empty(len(group), dtype=object)
        u = r.random(len(group))
        for gi in range(len(GROUPS)):
            m = group == gi
            out[m] = self.surnames[np.minimum(np.searchsorted(self.surname_cum[gi], u[m], side="right"), len(self.surnames) - 1)]
        return out

    def first_name(self, r: np.random.Generator, group: np.ndarray, male: np.ndarray, birth_year: np.ndarray) -> np.ndarray:
        u = r.random(len(group))
        if self.first is None:
            k = np.where(male, (u * len(self.fallback_m)).astype(int), (u * len(self.fallback_f)).astype(int))
            return np.where(male, self.fallback_m[np.minimum(k, len(self.fallback_m) - 1)],
                            self.fallback_f[np.minimum(k, len(self.fallback_f) - 1)])
        decades = sorted({d for _, d, _ in self.first})
        dec = np.clip((np.asarray(birth_year) // 10) * 10, decades[0], decades[-1])
        out = np.empty(len(group), dtype=object)
        keys = pd.DataFrame({"sex": np.where(male, "M", "F"), "dec": dec, "g": group})
        for (sex, d, gi), idx in keys.groupby(["sex", "dec", "g"]).indices.items():
            names, cum = self.first.get((sex, int(d), int(gi))) or self.first[(sex, int(d), 0)]
            out[idx] = names[np.minimum(np.searchsorted(cum, u[idx], side="right"), len(names) - 1)]
        return out
