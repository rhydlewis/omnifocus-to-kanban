from converter import Converter
import logging

log = logging.getLogger(__name__)

TODO_LANE = "Todo"
DOING_LANE = "Doing"
DONE_LANE = "Done"

class LeankitCard(Converter):
    attributes = ['Id', 'Title', 'Priority', 'Description', 'Tags', 'TypeId']
    optional_attributes = ['ExternalCardID', 'AssignedUserId', 'Size', 'IsBlocked', 'BlockReason',
                           'ExternalSystemName', 'ExternalSystemUrl', 'ClassOfServiceId',
                           'DueDate', 'CurrentTaskBoardId', 'TaskBoardTotalSize',
                           'ParentTaskboardId']

    # def __str__(self):
    #     return unicode(self.title)
    #
    # def __repr__(self):
    #     repr = "<LeankitCard " + self.external_card_id + " '" + unicode(self.title) + "'"
    #     print repr
    #     return repr

    def __init__(self, card_dict, lane):
        super(LeankitCard, self).__init__(card_dict)

        self.lane = lane
        self.tags_list = set()
        self._tasks_with_external_ids = []
        self._tasks = []
        self._default_taskboard_lane = None
        self.type = lane.board.card_types[self.type_id]
        if self.has_tasks():
            self.classify_taskboard_cards(self.lane.board.connector)

    @property
    def is_new(self):
        return self.id is None

    def save(self):
        if not (self.is_dirty or self.is_new):
            # no-op.
            return
        data = self._raw_data
        data["UserWipOverrideComment"] = None
        if "AssignedUsers" in data and "assigned_user_id" not in self.dirty_attrs:
            if 'AssignedUserId' in data.keys():
                del data['AssignedUserId']
            if 'AssignedUserName' in data.keys():
                del data['AssignedUserName']
            data['AssignedUserIds'] = map(
                lambda X: X['AssignedUserId'], data['AssignedUsers'])

        for attr in self.dirty_attrs:
            data[self._to_camel_case(attr)] = getattr(self, attr)

        if self.is_new:
            del data['Id']
            del data['LaneId']
            position = len(self.lane.cards)
            url_parts = ['/Board', str(self.lane.board.id), 'AddCard',
                         'Lane', str(self.lane.id), 'Position', str(position)]
        else:
            url_parts = ['/Board', str(self.lane.board.id), 'UpdateCard']

        url = '/'.join(url_parts)

        result = self.lane.board.connector.post(url, data=data)

        from connector import SUCCESS_CODES
        if self.is_new and result.ReplyCode in SUCCESS_CODES:
            self.id = result.ReplyData[0]['CardId']
            self._taskboard_request_url = "/v1/Board/" + str(self.lane.board.id) + "/card/" + \
                                          str(self.id) + "/taskboard"

        return result.ReplyData[0]

    @classmethod
    def create(cls, lane):
        default_card_data = {
            'Id': None,
            'Title': '',
            'Priority': 1,
            'Description': '',
            'Tags': '',
            'TypeId': lane.board.default_card_type.id,
            'LaneId': lane.id,
            'IsBlocked': "false",
            'BlockReason': None,
            'ExternalCardID': None,
            'ExternalSystemName': None,
            'ExternalSystemUrl': None,
            'ClassOfServiceId': None,
        }
        card = cls(default_card_data, lane)
        return card

    # @TODO
    def _add_task(self, task):
        log.info(u"Adding sub task '{0}' to {1}".format(task['name'], self.title))
        pass

        external_id = task['identifier']
        if external_id in self._tasks_with_external_ids:
            return False

        name = task['name']
        identifier = task['identifier']
        note = task['note']
        card_type = task['type']
        type_id = self.lane.board.determine_card_type_id(task['type'])
        log.info("Creating card with details: name={0} id={1} type={2} ({3})".format(
            name, identifier, card_type, type_id))

        if not self._default_taskboard_lane:
            self._default_taskboard_lane = self._get_default_taskboard_lane()

        new_card = self._default_taskboard_lane.add_card()
        new_card.title = name
        new_card.external_card_id = identifier
        if note:
            new_card.description = note
        if type_id:
            new_card.type_id = type_id
        new_card.is_blocked = 'false'
        new_card.save()

        # Refresh tasks with ids
        self._tasks_with_external_ids = [card.external_card_id for card in self._tasks
                                         if len(card.external_card_id) > 1]

    def has_tasks(self):
        return self.task_board_total_size > 0

    def tasks_with_external_ids(self, lanes=None):
        cards = []
        if lanes:
            [cards.extend([card.external_card_id for card in self.tasks
                           if len(card.external_card_id) > 1 and card.lane.title in lanes])]
        else:
            cards = self._tasks_with_external_ids
        return cards

    def add_tasks(self, tasks):
        for task in tasks:
            result = self._add_task(task)

            if not result:
                log.debug("Not adding sub-task {0} {1}, it's already in the task board".
                          format(task.external_card_id, task.title))

    def classify_taskboard_cards(self, connector):
        from lane import LeankitLane
        log.debug("Looking for tasks within taskboard of {0} {1}".format(self.external_card_id,
                                                                         self.title))

        try:
            taskboard_lanes = self._get_taskboard_lanes()
            for lane_dict in taskboard_lanes:
                lane = LeankitLane(lane_dict, self.lane.board)

                if lane.title == TODO_LANE:
                    self._default_taskboard_lane = lane

                tasks = lane.cards

                for task in tasks:
                    external_id = task.external_card_id
                    log.debug("Found card {0} {1} in taskboard lane {2} {3}".format(external_id,
                                                                                    task.title,
                                                                                    lane.id,
                                                                                    lane.title))
                    if external_id:
                        self._tasks_with_external_ids.append(task)

                    self._tasks.append(task)
        except IOError as e:
            log.info("Failed to get taskboard for {0}".format(self.title))

    def _get_default_taskboard_lane(self):
        from lane import LeankitLane

        for lane_dict in self._get_taskboard_lanes():
            lane = LeankitLane(lane_dict, self.lane.board)
            if lane.title == TODO_LANE:
                return lane

    def _get_taskboard_lanes(self):
        try:
            return self.lane.board.connector.get(self._taskboard_url()).ReplyData[0]['Lanes']
        except IOError as e:
            log.info("Failed to get taskboard for {0}".format(self.title))
        return None

    def _taskboard_url(self):
        return "/v1/Board/" + str(self.lane.board.id) + "/card/" + str(self.id) + "/taskboard"