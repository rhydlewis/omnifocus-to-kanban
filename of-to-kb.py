#!/usr/bin/env python

"""Omnifocus to Kanban

Usage:
  of-to-kb.py
  of-to-kb.py -h | --help
  of-to-kb.py --version

"""

import logging
import sys
import os

from docopt import docopt

from omnifocus import Omnifocus
from kanban_board import LeanKit


def main():
    docopt(__doc__)

    logging.info("omnifocus-to-kanban started...")
    logging.info("Current working directory: {0}".format(os.getcwd()))

    board = LeanKit()
    omnifocus = Omnifocus()

    external_ids = board.find_completed_card_ids()
    omnifocus.close_tasks([external_id for external_id in external_ids])

    tasks = omnifocus.flagged_tasks()
    new_tasks = []
    for task in tasks:
        identifier = task['identifier']
        name = task['name']
        if not board.card_exists(identifier):
            logging.debug("Adding {0} ({1}) to list of tasks to sync with board".format(name, identifier))
            new_tasks.append(task)
        else:
            logging.debug("Ignoring {0} ({1}) since it's already on the board".format(name, identifier))
    if len(new_tasks) > 0:
        board.add_cards(new_tasks)
    else:
        logging.info("Board is up to date - no cards to sync")


def _init_logging():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                        datefmt='%y-%m-%d %H:%M:%S', filename='omnifocus-to-kanban.log', filemode='w')
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter('%(message)s'))
    logging.getLogger('').addHandler(console)


if __name__ == '__main__':
    _init_logging()
    main()
