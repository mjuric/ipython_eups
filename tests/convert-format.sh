#!/bin/bash
#
# Run this script with IPython >= 3.0 to generate notebooks that 1.1 and 2.0
# can read. These can be used to test whether the code works with older IPythons
#

ipython nbconvert --to notebook --nbformat 3 --output python-1.1 python-3.0
ipython nbconvert --to notebook --nbformat 3 --output python-2.1 python-3.0
