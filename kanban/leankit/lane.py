from converter import Converter
from card import LeankitCard
import logging

log = logging.getLogger(__name__)


class LeankitLane(Converter):
    attributes = ['Id', 'Title', 'Index', 'Orientation', 'ParentLaneId']
    optional_attributes = ['Type', 'IsDefaultDropLane']

    def __init__(self, lane_dict, board):
        super(LeankitLane, self).__init__(lane_dict)
        self.parent_lane = None
        self.board = board
        self.child_lanes = []
        self.cards = [LeankitCard(card_data, self) for card_data in lane_dict['Cards']
                      if card_data['TypeId']]

    def add_card(self):
        card = LeankitCard.create(self)
        self.cards.append(card)
        return card
