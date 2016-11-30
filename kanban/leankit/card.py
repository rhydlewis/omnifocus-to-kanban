from converter import Converter
from task import LeankitTask
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
        identifier = task['identifier']
        if self.has_task(identifier):
            return False

        if task['completed']:
            log.debug("Ignoring completed sub task '{0}'".format(task['name']))
            return False
        else:
            log.debug("Adding sub task '{0}' to {1}".format(task['name'], self.title))

        name = task['name']
        note = task['note']
        card_type = task['type']
        type_id = self.lane.board.determine_card_type_id(task['type'])
        log.info("Creating task with details: name={0} id={1} type={2} ({3})".format(
            name, identifier, card_type, type_id))

        new_task = LeankitTask.create(self)
        new_task.title = name
        new_task.description = note
        new_task.external_card_id = identifier
        new_task.type_id = type_id
        new_task.save()

        self._tasks.append(new_task)

    def has_tasks(self):
        return self.task_board_total_size > 0

    def has_task(self, identifier):
        result = False
        for task in self._tasks:
            if task.external_card_id == identifier:
                result = True
        return result

    def tasks_with_external_ids(self):
        tasks = []
        for card in self._tasks:
            if card.external_card_id:
                tasks.append(card)
        return tasks

    def add_tasks(self, tasks):
        for task in tasks:
            result = self._add_task(task)

            if not result:
                log.debug("Not adding sub-task {0} {1}, it's already in the task board".
                          format(task['identifier'], task['name']))

    def classify_taskboard_cards(self, connector):
        from lane import LeankitLane

        title = self.title
        print ("Looking for tasks within taskboard of {0} {1}".format(self.external_card_id,
                                                                         self.title))

        log.debug("Looking for tasks within taskboard of {0} {1}".format(self.external_card_id,
                                                                         self.title))

        try:
            taskboard_lanes = self._get_taskboard_lanes()
            for lane_dict in taskboard_lanes:
                lane = LeankitLane(lane_dict, self.lane.board)
                tasks = lane.cards

                for task in tasks:
                    external_id = task.external_card_id
                    log.debug(u"Found task {0} {1} in taskboard lane {2} {3}".format(external_id,
                                                                                     task.title,
                                                                                     lane.id,
                                                                                     lane.title))
                    if external_id:
                        self._tasks_with_external_ids.append(task)

                    self._tasks.append(task)
        except IOError as e:
            log.info("Failed to get taskboard for {0}".format(self.title))

    def _get_taskboard_lanes(self):
        try:
            return self.lane.board.connector.get(self._taskboard_url()).ReplyData[0]['Lanes']
        except IOError as e:
            log.info("Failed to get taskboard for {0}".format(self.title))
        return None

    def _taskboard_url(self):
        return "/v1/Board/" + str(self.lane.board.id) + "/card/" + str(self.id) + "/taskboard"
