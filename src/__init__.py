import numpy as np

# Compatibility patch: pandas_ta requires np.NaN which was deprecated in numpy >= 2.0
if not hasattr(np, "NaN"):
    np.NaN = np.nan
