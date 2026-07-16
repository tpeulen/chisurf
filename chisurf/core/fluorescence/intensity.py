from __future__ import annotations


def nusiance(
        f,
        *args,
        **kwargs
):
    """Inject intensity/anisotropy correction globals into the wrapped function.

    :param Ss: perpenticular signal
    :param Sp: parallel signal
    :param Bs: perpenticular background
    :param Bp: parallel background
    :param Gfactor: g-factor
    :param l1: Objective mixing correction factor
    :param l2: Objective mixing correction factor
    :return: Anisotropy
    """

    def m(*args, **kwargs):
        """Set the correction globals, then call the wrapped function."""
        # ``__globals__`` is the Python-3 name of the (Python-2) ``func_globals``
        # attribute; using the old name raised AttributeError at call time.
        g = f.__globals__

        # Anisotropy
        g['Gfactor'] = kwargs.get('Gfactor', 1.0)
        g['Bp'] = kwargs.get('Bp', 0.0)
        g['Bs'] = kwargs.get('Bs', 0.0)
        g['l1'] = kwargs.get('l1', 0.0)
        g['l2'] = kwargs.get('l2', 0.0)

        # Intensities
        g['Bg'] = kwargs.get('Bg', 0.0)
        g['Br'] = kwargs.get('Br', 0.0)
        g['crosstalk'] = kwargs.get('crosstalk', 0.0)

        g['phiA'] = kwargs.get('phiA', 1.0)
        g['phiD'] = kwargs.get('phiD', 1.0)

        g['R0'] = kwargs.get('R0', 52.0)

        return f(*args, **kwargs)

    return m


