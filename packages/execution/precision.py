"""Exchange price / quantity precision helpers.

Hard-coding `round(price, 2)` breaks every symbol trading below ~$10 (e.g. DOGE at
0.1500 would round a 1.5% stop of 0.14775 up to 0.15, i.e. onto the entry price).
These helpers round to the exchange-provided precision when known, and otherwise to
a significant-digit based fallback that is safe for any price magnitude.
"""

import math
from decimal import Decimal, InvalidOperation
from typing import Optional

DEFAULT_SIGNIFICANT_DIGITS = 6
DEFAULT_QTY_DECIMALS = 4


def fallback_price_decimals(price: float, significant_digits: int = DEFAULT_SIGNIFICANT_DIGITS) -> int:
    """Decimal places that keep `significant_digits` significant digits (never fewer than 2)."""
    if not price or not math.isfinite(price) or price <= 0:
        return 2
    magnitude = int(math.floor(math.log10(abs(price))))
    return max(2, significant_digits - 1 - magnitude)


def decimals_from_step(step: object) -> Optional[int]:
    """Convert an exchange step / tick size such as '0.001' or 1e-05 into decimal places."""
    try:
        d = Decimal(str(step)).normalize()
    except (InvalidOperation, ValueError, TypeError):
        return None
    if d <= 0:
        return None
    exponent = d.as_tuple().exponent
    return max(0, -int(exponent)) if isinstance(exponent, int) else None


def round_price(price: float, decimals: Optional[int] = None) -> float:
    """Round a trigger / limit price to `decimals`, or to the significant-digit fallback."""
    if decimals is None:
        decimals = fallback_price_decimals(price)
    return round(float(price), int(decimals))


def floor_quantity(quantity: float, decimals: Optional[int] = None) -> float:
    """Round a quantity DOWN to the allowed decimals so orders never exceed balance or position."""
    if decimals is None:
        decimals = DEFAULT_QTY_DECIMALS
    factor = 10 ** int(decimals)
    # The epsilon absorbs binary float noise such as 0.0065 * 1e4 = 64.99999999.
    return math.floor(float(quantity) * factor + 1e-9) / factor
