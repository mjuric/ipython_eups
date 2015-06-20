#!/bin/bash
#
# Usage: make_distrib.sh [--publish]
#
# If --publish is specify, scp the result so it's visible as
# http://eupsforge.net/ipython
#

set -e

DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

BIN_IPYTHON="$DIR/../bin/ipython"
EUPS_MAGIC="$DIR/../python/eups_magic.py"

DISTRIB_IPYTHON="$DIR/ipython"

EUPSFORGE_PATH="mjuric@lsst-dev.ncsa.illinois.edu:public_html/eupsforge/ipython"

# This must be the same as the eponymous variable in $BIN_IPYTHON script
MAGIC="EMBEDDED""_PYTHON_MODULE----------"

# Check we can orient ourselves
if [[ ! -f "$BIN_IPYTHON" || ! -f "$EUPS_MAGIC" ]]; then
	echo "$BIN_IPYTHON or $EUPS_MAGIC not found. Exiting."
	exit -1
fi

# Copy ipython, inserting version
head -n 1 "$BIN_IPYTHON" > "$DISTRIB_IPYTHON"
echo "#" >> "$DISTRIB_IPYTHON"
echo "# GENERATED FILE. DO NOT EDIT. THE SOURCE IS IN bin/ipython" >> "$DISTRIB_IPYTHON"
echo "# THIS FILE WAS GENERATED WITH $(basename $0)." >> "$DISTRIB_IPYTHON"
echo "#" >> "$DISTRIB_IPYTHON"
echo "# git describe version: $(git describe --always --dirty)" >> "$DISTRIB_IPYTHON"
echo "#" >> "$DISTRIB_IPYTHON"
tail +2 "$BIN_IPYTHON" >> "$DISTRIB_IPYTHON"
chmod +x "$DISTRIB_IPYTHON"

echo "exit" >> "$DISTRIB_IPYTHON"
echo >> "$DISTRIB_IPYTHON"
echo "$MAGIC" >> "$DISTRIB_IPYTHON"
cat "$EUPS_MAGIC" >> "$DISTRIB_IPYTHON"

echo "The packed script has been created in $DISTRIB_IPYTHON"

if [[ "$1" == "--publish" ]]; then
	echo "Publishing to EUPSForge (http://eupsforge.net/ipython):"
	scp "$DISTRIB_IPYTHON" "$EUPSFORGE_PATH"
fi
