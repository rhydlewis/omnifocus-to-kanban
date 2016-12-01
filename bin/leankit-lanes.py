#!/usr/bin/env python
import sys
import os
import logging
import logging.config
sys.path.insert(0, '.')
from kanban import LeanKit


def main():
    lk = LeanKit()
    board_id = lk.config['board_id']
    print "Lane ID's for board {0}".format(board_id)
    lanes = lk.board.lanes
    for key in lanes:
        lane = lanes[key]
        print "{0}: {1}".format(lane.id, lane.title)


if __name__ == '__main__':
    logging.config.fileConfig('config/log.conf')
    logging.debug("sys.path: %s", sys.path)
    logging.debug("sys.executable: %s", sys.executable)
    logging.debug("os.getcwd(): %s", os.getcwd())

    main()


