# -*- coding: utf-8 -*-
"""
Setbacks CLI
"""
import logging

from gaps.cli import make_cli

from reVX.exclusions.setbacks._cli import (setbacks_command,
                                           merge_setbacks_command)
from reVX import __version__


logger = logging.getLogger(__name__)

commands = [
    setbacks_command,
    merge_setbacks_command,
]

cli = make_cli(commands)


if __name__ == '__main__':
    try:
        cli(obj={})
    except Exception:
        logger.exception('Error running Setbacks CLI')
        raise
