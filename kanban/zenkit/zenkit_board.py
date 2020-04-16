import requests
from requests import RequestException
import logging


class ZenKitBoard:
    log = logging.getLogger(__name__)
    api_requests = 0
    all_tasks = {}
    completed_tasks = []
    labels = {}
    stages = {}

    def __init__(self, token):
        self.headers = {'Zenkit-API-Key': "{0}".format(token), 'Content-Type': 'application/json'}
        self.classify_board()

    def classify_board(self):
        list_elements = self.get("https://base.zenkit.com/api/v1/lists/1002035/elements").json()
        self.labels = self.get_element_data(list_elements, 'Label')
        self.stages = self.get_element_data(list_elements, 'Stage')

        items = self.post("https://base.zenkit.com/api/v1/lists/D8G_kkAr3/entries/filter/list", None).json()
        for item in items['listEntries']:
            is_completed = False
            name = item['displayString']
            # swimlane = item['6ec8c6d4-5c72-47c0-acfe-219777410421_categories_sort'][0]['name']
            omnifocus_id = item['2a8c67c6-4c8a-4f49-b7aa-a7ae5a302f7d_text']
            self.all_tasks[omnifocus_id] = item

            try:
                if "Done" in item['2ed6b6dd-d957-4426-a5d1-8b7417603229_categories_sort'][0]['name']:
                    is_completed = True
            except IndexError:
                self.log.debug(u"{0} not in a recognised column".format(name))

            if is_completed:
                self.completed_tasks.append({"id": omnifocus_id, "name": name})

    def get_element_data(self, data, key):
        map = {}
        elements = [list_el for list_el in data if list_el['name'] == key]

        for element in elements[0]['elementData']['predefinedCategories']:
            name = element['name']
            _id = element['id']
            map[name] = _id

        return map

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
                self.log.debug(u"Ignoring '{0}' as it already exists".format(name))
                # tasks_added += self.update_task(identifier, name, note, subtasks)
            else:
                tasks_added += self.create_item(name, identifier, note, _type)

        return tasks_added

    def create_item(self, name, of_id, note, _type):
        if 'None' == _type:
            raise ValueError("Task '{0}' can't have context value of 'None'".format(name))

        updates_made = 0

        properties = {}
        properties["sortOrder"] = "lowest"
        properties["checklists"] = []

        json = self.post("https://base.zenkit.com/api/v1/lists/1002035/entries", properties).json()
        self.log.debug(u"{0}".format(json))

        list_id = json['listId']
        short_id = json['shortId']

        updates = {'updateAction': 'replace'}
        updates['debc1fa9-6a4e-4ed5-bbef-a1ee8ebc9eeb_text'] = name
        updates['6f6d8ab3-6ebe-4b85-83a7-9fd91bd26838_text'] = _type
        updates['ada6d48c-a778-480c-84ad-819248162b7d_text'] = note
        updates['2a8c67c6-4c8a-4f49-b7aa-a7ae5a302f7d_text'] = of_id
        updates['6ec8c6d4-5c72-47c0-acfe-219777410421_categories'] = [self.labels['work']]
        updates['2ed6b6dd-d957-4426-a5d1-8b7417603229_categories'] = [self.stages['To-Do']]

        url = "https://base.zenkit.com/api/v1/lists/{0}/entries/{1}".format(list_id, short_id)

        self.put(url, updates).json()
        updates_made += 1

        return updates_made

    def post(self, url, body=None):
        if body:
            response = requests.post(url, headers=self.headers, json=body)
        else:
            response = requests.post(url, headers=self.headers)

        self.api_requests += 1
        return response

    def put(self, url, body):
        response = requests.put(url, headers=self.headers, json=body)
        self.api_requests += 1
        return response

    def get(self, url):
        response = requests.get(url, headers=self.headers)
        self.api_requests += 1
        return response
