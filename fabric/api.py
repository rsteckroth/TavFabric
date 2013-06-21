"""
Non-init module for doing convenient * imports from.

Necessary because if we did this in __init__, one would be unable to import
anything else inside the package -- like, say, the version number used in
setup.py -- without triggering loads of most of the code. Which doesn't work so
well when you're using setup.py to install e.g. paramiko!
"""
from fabric.context import TIMEOUT, failed, shell, succeeded
from fabric.context_managers import cd, hide, path, prefix, settings, show
from fabric.decorators import hosts, roles, run_once, runs_once, task
from fabric.operations import (
    execute, get, local, open_shell, prompt, put, reboot, require, run, sudo
    )
from fabric.state import env, output
from fabric.utils import abort, fastprint, puts, warn
