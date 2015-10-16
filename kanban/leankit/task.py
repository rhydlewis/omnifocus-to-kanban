from converter import Converter
import logging

log = logging.getLogger(__name__)


class LeankitTask(Converter):
    attributes = ['Id', 'Title', 'Priority', 'Description', 'Tags', 'TypeId']
    optional_attributes = ['ExternalCardID']

    def __init__(self, task_dict, parent):
        super(LeankitTask, self).__init__(task_dict)

        self.parent = parent
        self.type = parent.lane.board.card_types[self.type_id]

    @classmethod
    def create(cls, parent):
        default_task_data = {
            'Id': None,
            'Title': '',
            'Priority': 1,
            'Description': '',
            'Tags': '',
            'TypeId': parent.lane.board.default_card_type.id,
            'LaneId': parent.lane.id,
            'IsBlocked': "false",
            'BlockReason': None,
            'ExternalCardID': None,
            'ExternalSystemName': None,
            'ExternalSystemUrl': None,
            'ClassOfServiceId': None,
        }
        task = cls(default_task_data, parent)
        return task

    def save(self):
        data = self._raw_data
        data["UserWipOverrideComment"] = None

        for attr in self.dirty_attrs:
            data[self._to_camel_case(attr)] = getattr(self, attr)
        url_parts = ['/v1/Board', str(self.parent.lane.board.id), 'card', str(self.parent.id),
                     'tasks/lane', str(0), 'position', str(0)]
        url = '/'.join(url_parts)

        del data['Id']
        result = self.parent.lane.board.connector.post(url, data=data)

        from connector import SUCCESS_CODES
        if result.ReplyCode in SUCCESS_CODES:
            self.id = result.ReplyData[0]['CardId']
        return result.ReplyData[0]
