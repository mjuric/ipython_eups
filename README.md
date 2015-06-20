# EUPS for IPython

## Overview

This is an IPython extension and a wrapper script that add a new magic
named `%eups` to IPython, which allows one to:

* initialize EUPS without restarting the notebook (i.e., the equivalent of
  sourcing setups.sh)

* setup EUPS products from within the notebook (i.e., the equivalent of
  running `setup foo` on the command line)

* call all other EUPS commands from within IPython (i.e., `eups list`
  or `eups distrib install`)

This comes in handy when one the Python notebook to fully capture the
products (possibly down to the product version) that were used to execute
it.

It's also especially useful when in the middle of data analysis one realizes
they've forgotten to setup a product that's needed at that point.

## Example

Setting up a specific version of the OpenOrb package:

    # Load the eups_magic extension (do this once per notebook)
    %load_ext eups_magic

    %eups setup oorb lsst-g650e0a6f6c

    import pyoorb

More examples and documentation are available in [the overview
notebook](doc/eups-magics-overview.ipynb) in the doc directory.

## Installing

Download the `ipython` pass-through script and place it somewhere on your
path (before the real ipython !). For example:

    wget http://eupsforge.net/ipython
    chmod +x ipython
    cp ipython ...somewhere/on/your/path...

This script will set up the environment required for `%eups` extension to
work, before transparently handing of control to your IPython interpreter.

More installation options are described in [the overview
notebook](doc/eups-magics-overview.ipynb) in the doc directory.
