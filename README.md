# EUPS for IPython

## Overview

This is an IPython extension and a wrapper script that add a new magic
named `%eups` to IPython, which allows one to:

* initialize [EUPS](https://github.com/RobertLuptonTheGood/eups) without
  restarting the notebook (i.e., the equivalent of sourcing setups.sh)

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

After starting `ipython` with `ipython-eups` support (see the next section),
to set up a specific version of the [OpenOrb](https://github.com/oorb/oorb)
product, run:

```python
# Load the eups_magic extension (do this once per notebook)
%load_ext eups_magic

%eups setup oorb lsst-g650e0a6f6c

import pyoorb
```

More examples and documentation are available in [the overview
notebook](doc/eups-magics-overview.ipynb) in the doc directory.

## Installing and Running

Download the `ipython-eups` script and run it any time you'd ordinarily run
IPython:

```bash
wget http://eupsforge.net/ipython-eups
chmod +x ipython-eups
```

This script sets up the environment required for `%eups` magic to work,
before transparently handing of control to your IPython interpreter.

You can also alias your `ipython` to `ipython-eups`:

```bash
alias ipython="...path/to/ipython-eups"	# bash, ksh, zsh
```

or

```csh
alias ipython "...path/to/ipython-eups"	# csh, tcsh
```

Appending these to your `.bashrc` (for `bash`) or `.cshrc` (for
`csh` and `tcsh`) will make this automatic.

## Compatibility

While the code is actively developed and regularly tested with IPython 3.0
only, any IPython version >= 1.1 should work (and problems will be
considered bugs).

## Developing

The sources are at http://github.com/mjuric/ipython_eups, and ipython-eups
is an EUPS product itself:

    git clone http://github.com/mjuric/ipython_eups
    setup -r ipython_eups

This is a pure python extenson, so no compilation is necessary. The `setup`
will add `./bin` (where the `ipython-eups` script) to `$PATH`, and
`./python` (where the IPython extension code is) to `$PYTHONPATH`.

To create a redistributable "packed" wrapper script that includes everything
needed to run ipython-eups (like the one distributed via
http://eupsforge.net), run:

    ./distrib/make_distrib.sh

The packed script will be created in `./distrib`. Running with `--publish`
will also publish it to eupsforge.net (assuming you have the permissions to
do so).
