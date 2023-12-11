import requests
import logging
import base64
from operator import itemgetter

COMMENT_PREFIX = "external_id="
TASKS_URI = "https://kanbanflow.com/api/v1/tasks/"


class KanbanFlowBoard:
    log = logging.getLogger(__name__)
    auth = None
    default_drop_column = None
    board_details = None
    all_tasks = {}
    completed_tasks = []
    api_requests = 0
    bytes_transferred = 0

    def __init__(self, token, default_drop_column, types, completed_columns):
        auth = base64.b64encode("apiToken:{0}".format(token).encode()).decode("utf-8")
        self.auth = {'Authorization': "Basic {0}".format(auth)}
        self.board_details = self.request("https://kanbanflow.com/api/v1/board")
        self.default_swimlane = self.board_details['swimlanes'][0]['uniqueId']
        self.default_drop_column = default_drop_column
        self.types = types
        self.classify_board(completed_columns)

    def classify_board(self, completed_columns):
        columns = self.request(TASKS_URI)

        for column in columns:
            column_id = column["columnId"]
            column_name = column["columnName"]
            tasks = column["tasks"]
            is_completed_column = column_id in completed_columns

            # self.log.debug(u"Found {0} tasks in {1} (completed column? {2})".format(len(tasks), column_name,
            #                                                                         is_completed_column))

            for task in tasks:
                _id = task["_id"]
                # self.log.debug("{0}".format("Parsing task {0}".format(task["name"])))
                comment = self.get_comment_containing_id(_id)

                if comment is not None:
                    external_id = comment["text"][len(COMMENT_PREFIX):]
                    self.all_tasks[external_id] = task
                    if is_completed_column:
                        self.completed_tasks.append({"id": external_id, "name": task["name"]})

    def get_comment_containing_id(self, _id):
        # self.log.debug("Looking for comments in task {0}".format(_id))
        try:
            comment_json = self.request(TASKS_URI + "{0}/comments".format(_id))
            if comment_json:
                comment = next((item for item in comment_json if COMMENT_PREFIX in item["text"]))
                if comment:
                    return comment
        except:
            self.log.warning("Failed to get comments for {0}".format(_id))
        return None

    def create_tasks(self, tasks):
        self.log.debug(u"Checking which of {0} tasks to add".format(len(tasks)))

        tasks_added = 0
        external_ids = self.all_tasks.keys()

        for task in tasks:
            name = task['name']
            identifier = task['identifier']
            _type = task['type']
            note = task['note']
            subtasks = None

            if 'children' in task:
                subtasks = task['children']

            if identifier in external_ids:
                tasks_added += self.update_task(identifier, name, note, subtasks)
            else:
                tasks_added += self.create_task(name, self.default_drop_column, identifier, None, note, _type,
                                                subtasks)

        return tasks_added

    def create_task(self, name, column, identifier, swimlane, description='', _type=None, subtasks=None):
        if 'None' == _type:
            raise ValueError("Task '{0}' can't have context value of 'None'".format(name))

        if description is None:
            self.log.error(u"Task description is None? {0}".format(name))
            description=""

        color = None
        if _type:
            type_config = self.types[_type]
            color = type_config['color']

            if 'column' in type_config:
                column = type_config['column']

        updates_made = 0

        if swimlane is None:
            swimlane = self.default_swimlane

        if "Look" in name:
            print("here")

        properties = {"name": name, "columnId": column, "description": description,
                      "color": color, "swimlaneId": swimlane}
        # properties = {"name": name, "columnId": column, "description": description,
        #               "color": color}
        comment = COMMENT_PREFIX + identifier

        json = self.request("https://kanbanflow.com/api/v1/tasks", properties)
        self.log.debug(u"{0}".format(json))
        if json is not None:
            self.log.debug(u"Adding task: {0}".format(properties))
            task_id = json["taskId"]
            updates_made += 1
            self.request(TASKS_URI + "{0}/comments".format(task_id), {"text": comment})
        else:
            self.log.error(u"Task add failed: {0}".format(properties))

        if subtasks:
            sorted_subtasks = sorted(subtasks, key=itemgetter('name'))
            for subtask in sorted_subtasks:
                self.log.debug(u"Adding subtask '{0}' to task {1} with id {2}".format(subtask, name, task_id))
                self.create_subtask(task_id, subtask)
                updates_made += 1

        return updates_made

    def delete_external_id_comment(self, identifier):
        task = self.all_tasks[identifier]
        task_id = task['_id']

        comment = self.get_comment_containing_id(task_id)

        if comment is not None:
            comment_id = comment["_id"]
            requests.delete(TASKS_URI + "{0}/comments/{1}".format(task_id, comment_id), headers=self.auth)

    def create_subtask(self, task_id, subtask):
        name = subtask['name']
        completed = subtask['completed']
        if not completed:
            completed = False
        uri = TASKS_URI + "{0}/subtasks".format(task_id)
        body = {"name": name, "finished": completed}
        json = self.request(uri, body)

    def update_task(self, identifier, name, note, subtasks=None):
        task = self.all_tasks[identifier]
        task_id = task['_id']
        existing_subtask_names = self.get_subtasks(task_id)
        properties = {}
        updates_made = 0

        if task['name'] != name:
            properties['name'] = name
        if compare_description(task['description'], note):
            properties['description'] = note

        if not len(properties) and not subtasks:
            self.log.debug(u"Nothing to update in task {0} '{1}'".format(identifier, name))
            return updates_made

        if len(properties):
            self.log.debug(u"Updating pre-existing task {0} '{1}'".format(identifier, name))
            self.request(TASKS_URI + "{0}".format(task_id), properties)
            updates_made += 1

        if subtasks:
            sorted_subtasks = sorted(subtasks, key=itemgetter('name'))
            self.log.debug(u"Existing sub-tasks in {0}, {1}: {2}".format(identifier, name, sorted_subtasks))
            for subtask in sorted_subtasks:
                subtask_name = subtask['name']
                if subtask_name not in existing_subtask_names:
                    self.log.debug(u"Adding new subtask '{0}' to '{1}'".format(subtask_name, name))
                    self.create_subtask(task_id, subtask)
                    updates_made += 1

        return updates_made

    def get_column_name(self, _id):
        columns = self.board_details["columns"]
        column = next(item for item in columns if item["uniqueId"] == _id)
        return column

    def clear_board(self):
        response = requests.get(TASKS_URI, headers=self.auth)

        for column in response:
            tasks = column["tasks"]
            for task in tasks:
                _id = task["_id"]
                requests.delete(TASKS_URI + "{0}".format(_id), headers=self.auth)

    def get_subtasks(self, task_id):
        names = []
        sub_tasks = self.request(TASKS_URI + "{0}/subtasks".format(task_id))
        for sub_task in sub_tasks:
            names.append(sub_task['name'])
        return names

    def request(self, url, body=None):
        try:
            if body:
                # self.log.debug("POST {0}".format(url))
                headers = self.auth.copy()
                headers['Accept-Encoding'] = "gzip"
                response = requests.post(url, headers=headers, json=body)
            else:
                # self.log.debug("GET {0}".format(url))
                response = requests.get(url, headers=self.auth)

            self.api_requests += 1
            self.bytes_transferred += len(response.content)

            code = response.status_code
            # self.log.debug("RESPONSE {0}".format(code))

            if code == 200:
                json = response.json()
                return json
        except (
                requests.ConnectionError,
                requests.exceptions.ReadTimeout,
                requests.exceptions.Timeout,
                requests.exceptions.ConnectTimeout,
        ) as e:
            print(e)

        return None


def compare_description(description, note):
    result = False
    if not note:
        note = u''

    if description != note:
        result = True

    return result
