"""
Motilitometer Package

A modular package for cell tracking and optical flow analysis in microscopy videos.

Modules:
    - cell_tracking: Cell detection and tracking using Norfair
    - dense_flow: Dense optical flow analysis with drift correction

    - motilitometer: Command-line interface and main execution logic
"""

from .cell_tracking import CellTracker
from .dense_flow import Denseflow
from .cli import main, parse_args, build_tracker_from_args, build_denseflow_from_args

__all__ = [
    'CellTracker',
    'Denseflow',
    'main',
    'parse_args',
    'build_tracker_from_args',
    'build_denseflow_from_args'
]

__version__ = '1.0.0'
__author__ = 'Motilitometer Team'
