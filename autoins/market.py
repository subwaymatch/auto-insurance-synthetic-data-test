"""The market the company sells into: how many households shop for cover, and how its prices compare.

Two things move new business from month to month. The number of households asking for a quote follows the
season and the year (config.SHOPPING_SEASONALITY, SHOPPING_YEAR). And the share of them who buy depends on how
the company's rate level stands against the market's (config.MARKET_RATE_CHANGE): a filed increase takes
effect on one day, while the market's rates drift up through the year, so each increase leaves the company
dearer than its competitors until they catch up, and it writes less new business in the meantime. The same
gap is the centre of every quote's competitive position (quotes.py) and nudges renewals (simulate.py).
"""
from __future__ import annotations

import numpy as np

from . import config as C
from .refdata import Calendar, normal_grid

_Z = normal_grid(64)


def gap(cal: Calendar, day) -> np.ndarray:
    """log(the company's rate level / the market's) on a day."""
    d = np.clip(np.asarray(day), 0, len(cal.rate_level) - 1)
    return np.log(cal.rate_level[d] / cal.market_level[d])


def bind_p(channel, log_ratio) -> np.ndarray:
    """Chance that a quote binds, given log(our premium / the best competing premium)."""
    p = np.array([C.QUOTE_CONVERSION[c] for c in C.CHANNELS])[channel]
    return 1 / (1 + np.exp(-(np.log(p / (1 - p)) - C.QUOTE_PRICE_ELASTICITY * np.asarray(log_ratio))))


def shopping(cal: Calendar, months: np.ndarray) -> np.ndarray:
    """Relative number of households asking for a quote in each month (months counted from the start month)."""
    mid = cal.day_of(months, 15)
    date = cal.date(mid)
    moy = date.astype("M8[M]").astype(int) % 12
    ys = sorted(C.SHOPPING_YEAR)
    anchors = [(np.datetime64(f"{y}-07-01") - cal.start).astype(int) for y in ys]
    return np.array(C.SHOPPING_SEASONALITY)[moy] * np.interp(mid, anchors, [C.SHOPPING_YEAR[y] for y in ys])


def conversion(cal: Calendar, months: np.ndarray) -> np.ndarray:
    """Expected share of quotes that bind, by channel (rows) and month (columns): quotes' competitive positions
    are spread around the month's gap between the company's rates and the market's."""
    g = gap(cal, cal.day_of(months, 15))
    x = g[None, :, None] + C.COMPETITOR_PRICE_SIGMA * _Z[None, None, :]
    return bind_p(np.arange(len(C.CHANNELS))[:, None, None], x).mean(axis=2)


def month_weights(cal: Calendar, n_months: int, shoppers: bool) -> np.ndarray:
    """Weights, by channel and month, of the month a household comes to the company: everyone who asks for a quote
    (shoppers) or those who buy (new business: shoppers times the month's conversion)."""
    months = np.arange(n_months)
    w = np.tile(shopping(cal, months), (len(C.CHANNELS), 1))
    return w if shoppers else w * conversion(cal, months)
