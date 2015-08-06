#!/usr/bin/env python

"""Omnifocus to Kanban

Usage:
  of-to-kb.py (--trello | --leankit)
  of-to-kb.py -h | --help
  of-to-kb.py --version

"""

import logging
import logging.config
import os

from docopt import docopt

from omnifocus import Omnifocus
from kanban_board import LeanKit, Trello


def main():
    opts = docopt(__doc__)

    logging.debug("Current working directory: {0}".format(os.getcwd()))

    if opts['--trello']:
        logging.info("Connecting to Trello board")
        board = Trello()
    elif opts['--leankit']:
        logging.info("Connecting to Leankit board")
        board = LeanKit()
    else:
        exit(-1)

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
    logging.config.fileConfig('log.conf')


if __name__ == '__main__':
    _init_logging()
    main()
