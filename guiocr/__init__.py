# -*- coding:utf-8 -*-
"""
Author: ZhangSY
Created time:2021/12/2 17:31
"""
import logging
import sys

from PyQt5.Qt import PYQT_VERSION_STR as QT_VERSION
# from qtpy import QT_VERSION

# QT_VERSION=PYQT_VERSION_STR
__appname__="ocr-demo"

# Semantic Versioning 2.0.0: https://semver.org/
# 1. MAJOR version when you make incompatible API changes;
# 2. MINOR version when you add functionality in a backwards-compatible manner;
# 3. PATCH version when you make backwards-compatible bug fixes.
__version__ = "1.1"


QT4 = QT_VERSION[0] == "4"
QT5 = QT_VERSION[0] == "5"
del QT_VERSION

PY2 = sys.version[0] == "2"
PY3 = sys.version[0] == "3"
del sys
