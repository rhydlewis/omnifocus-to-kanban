from leankit import LeankitKanban
import logging
import yaml
import os


class LeanKit:
    kb = None
    log = logging.getLogger(__name__)

    def __init__(self):
        self.config = self.load_config()
        board_id = self.config['board_id']
        self.kb = LeankitKanban(self.config['account'], self.config['email'], self.config['password'])
        self.log.debug("Connecting to Leankit board {0}".format(board_id))
        self.board = self.kb.getBoard(board_id=board_id)

    def find_completed_card_ids(self):
        lanes = self.config['completed_lanes']
        self.log.info("Looking for cards in completed lanes: {0}".format(lanes))
        cards = []

        [cards.extend([card.external_card_id for card in self.board.getLane(lane).cards
                       if len(card.external_card_id) > 1]) for lane in lanes]
        self.log.debug("Found {0} external ids".format(len(cards)))
        self.log.debug("External ids: {0}".format(cards))
        return cards

    def card_exists(self, identifier):
        return identifier in self.board.external_ids
        # return identifier in [card.external_card_id for card in self.board.cards_with_external_ids()]

    def add_cards(self, cards):
        self.board.add_cards(cards)
        return True

    def load_config(self):
        path = "{0}/leankit-config.yaml".format(os.getcwd())
        self.log.debug("Loading config file {0}".format(path))
        f = open(path)
        config = yaml.safe_load(f)
        f.close()
        return config
