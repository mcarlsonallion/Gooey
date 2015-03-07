#!/usr/bin/env bash

python setup.py sdist
python setup.py sdist bdist_wheel upload
