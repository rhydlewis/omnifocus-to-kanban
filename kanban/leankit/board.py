import logging
import operator
import re

from lane import LeankitLane
from connector import LeankitConnector
from converter import Converter

log = logging.getLogger(__name__)


ANNOTATION_REGEX = re.compile('^\s*\{.*}\s*$', re.MULTILINE | re.DOTALL)

log = logging.getLogger(__name__)


class LeankitUser(Converter):
    attributes = ['UserName', 'FullName', 'EmailAddress', 'Id']


class LeankitCardType(Converter):
    attributes = ['Name', 'IsDefault', 'ColorHex', 'IconPath', 'Id', 'IsTaskType']


class LeankitKanban(object):
    def __init__(self, account, email, password):
        self.connector = LeankitConnector(account, email, password)
        self._boards = []
        self._boards_by_id = {}
        self._boards_by_title = {}

    def get_boards(self, include_archived=False):
        """List all the boards user has access to.

        :param include_archived: if True, include archived boards as well.
        """
        boards_data = self.connector.get('/Boards').ReplyData
        boards = []
        for board_dict in boards_data[0]:
            board = LeankitBoard(board_dict, self.connector)
            if board.is_archived and not include_archived:
                continue
            boards.append(board)
        return boards

    def _refresh_boards_cache(self):
        self._boards = self.get_boards(True)
        self._boards_by_id = {}
        self._boards_by_title = {}
        for board in self._boards:
            self._boards_by_id[board.id] = board
            self._boards_by_title[board.title] = board

    def _find_board_in_cache(self, board_id=None, title=None):
        assert title is not None or board_id is not None, (
            "Either a board title or board id are required.")
        if board_id is not None and board_id in self._boards_by_id:
            return self._boards_by_id[board_id]
        elif title in self._boards_by_title:
            return self._boards_by_title[title]
        else:
            return None

    def _find_board(self, board_id=None, title=None):
        board = self._find_board_in_cache(board_id, title)
        if board is None:
            # Not found, try once more after refreshing the cache.
            self._refresh_boards_cache()
            board = self._find_board_in_cache(board_id, title)
        return board

    def get_board(self, board_id=None, title=None):
        board = self._find_board(board_id, title)
        if board is not None:
            board.fetch_details()
        return board


class LeankitBoard(Converter):
    attributes = ['Id', 'Title', 'CreationDate', 'IsArchived']
    base_uri = '/Boards/'

    def __init__(self, board_dict, connector):
        super(LeankitBoard, self).__init__(board_dict)

        self.connector = connector
        self.root_lane = LeankitLane({'Id': 0, 'Title': u'ROOT LANE', 'Index': 0,
                                      'Orientation': 0, 'ParentLaneId': -1, 'Cards': []}, self)
        self.lanes = {0: self.root_lane}
        self.cards = []
        self._cards_with_external_ids = set()
        self._done_taskboard_cards = set()
        self.default_card_type = None

    def add_cards(self, cards):
        lane = self.get_default_drop_lane()
        log.info("Checking which of the {0} cards to add to lane {1} ({2})".
                 format(len(cards), lane.title, lane.id))

        cards_added = 0

        for card in cards:
            name = card['name']
            identifier = card['identifier']
            child_tasks = None

            if card.has_key('children'):
                child_tasks = card['children']

            # Check if card exists on board already; if it does and has no child tasks; skip to next
            if identifier in self.external_ids and not child_tasks:
                logging.debug(u"Ignoring pre-existing card {0} '{1}'".format(identifier, name))
                continue
            elif identifier in self.external_ids and child_tasks:
                # process child tasks - look for those that don't exist and add them to the
                # pre-existing card
                logging.debug("Determining if existing card '{0}' has sub-tasks to add".
                              format(name))
                continue
                parent = self.get_card_with_external_id(identifier)
                parent.add_tasks(child_tasks)
                continue

            note = card['note']
            card_type = card['type']
            type_id = self.determine_card_type_id(card['type'])
            log.info("Creating card with details: name={0} id={1} type={2} ({3})".format(
                name, identifier, card_type, type_id))

            new_card = lane.add_card()
            new_card.title = name
            new_card.external_card_id = identifier
            if note:
                new_card.description = note
            if type_id:
                new_card.type_id = type_id
            new_card.is_blocked = 'false'
            new_card.save()
            cards_added += 1

            # TODO - this is wrong
            if child_tasks:
                new_card.add_tasks(child_tasks)
                cards_added += 1

    def determine_card_type_id(self, card_type):
        type_id = None
        try:
            type_id = self.card_type_names[card_type]
        except KeyError:
            log.info("Can't find card type {0} configured in LeanKit".format(card_type))

        return type_id

    def cards_with_external_ids(self, lanes=None):
        cards = []
        if lanes:
            [cards.extend([card.external_card_id for card in self.getLane(lane).cards
                           if len(card.external_card_id) > 1]) for lane in lanes]
        else:
            cards = self.external_ids
        return cards

    def done_taskboard_cards(self):
        return list([card.external_card_id for card in self._cards_with_external_ids
                     if card.parent_taskboard_id and card.lane.title == "Done"])

    def fetch_details(self):
        self.details = self.connector.get(self.base_uri + str(self.id)).ReplyData[0]
        self._populate_users(self.details['BoardUsers'])
        self._populate_card_types(self.details['CardTypes'])
        # self._archive = self.connector.get("/Board/" + str(self.id) + "/Archive").ReplyData[0]
        # archive_lanes = [lane_dict['Lane'] for lane_dict in self._archive]
        # archive_lanes.extend([lane_dict['Lane'] for lane_dict in self._archive[0]['ChildLanes']])
        self._backlog = self.connector.get("/Board/" + str(self.id) + "/Backlog").ReplyData[0]
        # self._populateLanes(self.details['Lanes'] + archive_lanes + self._backlog)
        self._populateLanes(self.details['Lanes'] + self._backlog)
        self._classify_cards()

    def _classify_cards(self):
        for card in self.cards:
            if card.external_card_id:
                self._cards_with_external_ids.add(card)

            if card.has_tasks():
                log.debug("Card '{0}' has {1} sub-tasks".format(card.title,
                                                                card.task_board_total_size))
                self._cards_with_external_ids |= set(card.tasks_with_external_ids())

        # log.debug("Found %s cards with external ids" % len(self._cards_with_external_ids))
        # log.debug("External ID's: {0}".format(self._cards_with_external_ids))
        self.external_ids = [card.external_card_id for card in self._cards_with_external_ids]

    def _populate_users(self, user_data):
        self.users = {}
        self.users_by_id = {}
        for user_dict in user_data:
            user = LeankitUser(user_dict)
            self.users[user.user_name] = user
            self.users_by_id[user.id] = user

    def _populateLanes(self, lanes_data):
        self.root_lane.child_lanes = []
        for lane_dict in lanes_data:
            lane = LeankitLane(lane_dict, self)
            self.lanes[lane.id] = lane
        for lane_id, lane in self.lanes.iteritems():
            if lane.id == 0:
                # Ignore the hard-coded root lane.
                continue
            else:
                lane.parent_lane = self.lanes.get(lane.parent_lane_id, None)
                lane.parent_lane.child_lanes.append(lane)
            log.debug("Lane {0} contains {1} cards".format(lane.title, len(lane.cards)))
            self.cards.extend(lane.cards)
        self._sortLanes()

    def _populate_card_types(self, card_types_data):
        self.card_types = {}
        for cardtype_dict in card_types_data:
            card_type = LeankitCardType(cardtype_dict)
            self.card_types[card_type.id] = card_type
            if card_type.is_default:
                self.default_card_type = card_type

        self.card_type_names = dict([(v.name, k) for k, v in self.card_types.iteritems()])

        assert self.default_card_type is not None

    def _sortLanes(self, lane=None):
        """Sorts the root lanes and lists of child lanes by their index."""
        if lane is None:
            lane = self.root_lane
        lanes = lane.child_lanes
        lanes.sort(key=operator.attrgetter('index'))
        for lane in lanes:
            self._sortLanes(lane)

    def getLane(self, lane_id):
        flat_lanes = {}

        def flatten_lane(lane):
            flat_lanes[lane.id] = lane
            for child in lane.child_lanes:
                flatten_lane(child)

        map(flatten_lane, self.root_lane.child_lanes)
        return flat_lanes[lane_id]

    def get_default_drop_lane(self):
        for lane in self.lanes.values():
            if lane.is_default_drop_lane:
                return lane
        return None

    def get_card_with_external_id(self, identifier):
        for item in self._cards_with_external_ids:
            if item.external_card_id == identifier:
                return item

        raise KeyError("Couldn't find card {0}".format(identifier))