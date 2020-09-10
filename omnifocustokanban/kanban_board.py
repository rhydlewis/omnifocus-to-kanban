import logging
import yaml
import os
from .bin import KanbanFlowBoard


class KanbanFlow:
    kb = None
    log = logging.getLogger(__name__)

    def __init__(self):
        self.config = load_config("config/kanbanflow-config.yaml")

        token = self.config['token']
        default_drop_lane = self.config['default_drop_lane']
        types = self.config['card_types']
        completed_columns = self.config['completed_lanes']

        self.kb = KanbanFlowBoard(token, default_drop_lane, types, completed_columns)

    def find_completed_card_ids(self):
        return self.kb.completed_tasks

    def card_exists(self, identifier):
        return identifier in self.kb.all_tasks

    def add_cards(self, cards):
        cards_added = self.kb.create_tasks(cards)
        self.log.debug("Made {0} API requests in this session".format(self.kb.api_requests))
        return cards_added

    def remove_comments_from_repeating_tasks(self, identifiers):
        for _id in identifiers:
            self.kb.delete_external_id_comment(_id['id'])


def load_config(path):
    path = "{0}/{1}".format(os.getcwd(), path)
    logging.debug("Loading config file {0}".format(path))
    f = open(path)
    config = yaml.safe_load(f)
    f.close()
    return config
