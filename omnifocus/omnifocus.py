# Based heavily on this: https://github.com/msabramo/PyOmniFocus

import applescript
import logging
import os
import re
from datetime import datetime

import sqlite3

# DB_LOCATION = ("/Library/Containers/com.omnigroup.OmniFocus2/"
#                "Data/Library/Caches/com.omnigroup.OmniFocus2/OmniFocusDatabase2")
#DB_LOCATION = "/Library/Containers/com.omnigroup.OmniFocus3/Data/Library/Application Support/" \
#              "OmniFocus/OmniFocus Caches/OmniFocusDatabase"
DB_LOCATION = "/Library/Group Containers/34YW5XSRB7.com.omnigroup.OmniFocus/com.omnigroup.OmniFocus3/com.omnigroup.OmniFocusModel/OmniFocusDatabase.db"
DB_PREFIX = ''
URI_PREFIX = 'omnifocus:///task/'
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
ENCODING = 'utf-8'

IS_TASK_COMPLETE = """
        on task_completed(task_id)
            tell application "OmniFocus"
                try
                    set theTask to task id task_id of default document
                    return completed of theTask
                end try
            end tell
        end run
    """
CLOSE_TASK = """
        on close_task(task_id)
            tell application "OmniFocus"
                set completed_task to task id task_id of default document
                set task_title to name of completed_task
                mark complete completed_task
            end tell
        end run
    """

FLAGGED_TASKS_SQL = """
SELECT Task.persistentIdentifier,
       Task.name,
       Task.plainTextNote,
       Task.containingProjectInfo,
       Task.blocked,
       Task.blockedByFutureStartDate,
       Task.flagged,
       Task.effectiveFlagged,
       Task.dateCompleted,
       Task.dateDue,
       Task.dateToStart,
       Task.effectiveDateToStart,
       Task.childrenCount,
       Task.repetitionMethodString,
       Task.containsNextTask,
       ProjectInfo.status,
       Context.name AS "tag"
FROM Task
JOIN TaskToTag ON TaskToTag.task = Task.persistentIdentifier
JOIN Context ON Context.persistentIdentifier = TaskToTag.tag
JOIN ProjectInfo ON ProjectInfo.task = Task.containingProjectInfo
WHERE Task.flagged = 1
  AND Task.effectiveFlagged = 1
  AND Task.dateCompleted IS NULL
  AND Task.blockedByFutureStartDate IS 0
  AND ProjectInfo.status NOT IN ('done',
                                 'dropped',
                                 'inactive')
"""

CHILD_TASKS_SQL = """
SELECT Task.persistentIdentifier,
       Task.name,
       Task.plainTextNote,
       Task.containingProjectInfo,
       Task.blocked,
       Task.blockedByFutureStartDate,
       Task.flagged,
       Task.effectiveFlagged,
       Task.dateCompleted,
       Task.dateDue,
       Task.dateToStart,
       Task.effectiveDateToStart,
       Task.childrenCount,
       Task.repetitionMethodString,
       Task.containsNextTask,
       ProjectInfo.status,
       Context.name AS "tag"
FROM Task
JOIN TaskToTag ON TaskToTag.task = Task.persistentIdentifier
JOIN Context ON Context.persistentIdentifier = TaskToTag.tag
JOIN ProjectInfo ON ProjectInfo.task = Task.containingProjectInfo
WHERE Task.dateCompleted IS NULL
  AND Task.blockedByFutureStartDate IS 0
  AND ProjectInfo.status NOT IN ('done',
                                 'dropped',
                                 'inactive')
  AND Task.parent = '{0}'
"""


class Omnifocus:
    log = logging.getLogger(__name__)

    def __init__(self):
        self.of_location = "{0}{1}".format(os.path.expanduser("~"), DB_LOCATION)
        if not os.path.isfile(self.of_location):
            self.of_location = re.sub(".OmniFocus3", ".OmniFocus3.MacAppStore", self.of_location)
        self.log.debug("Using Omnifocus location {0}".format(self.of_location))

        self.conn = sqlite3.connect(self.of_location)
        self.conn.row_factory = sqlite3.Row

    def flagged_tasks(self):
        self.log.debug("Looking for flagged tasks")

        tasks = dict()

        cursor = self.conn.cursor()
        cursor.execute(FLAGGED_TASKS_SQL)
        results = cursor.fetchall()
        self.log.debug("Found {0} results".format(len(results)))
        cursor.close()

        for row in results:
            task = Omnifocus.task_from_row(row)
            child_count = task['child_count']
            name = task['name']
            held = task['is_wf_task']
            _id = task['identifier']
            start_date = task['start_date'] # timestamp in OmniFocus 3.6

            if self.is_deferred(start_date):
                self.log.debug(u"Ignoring deferred task '{0}'".format(name))
                continue
            if (child_count and not task['has_next_task']) and (child_count and not held):
                self.log.debug(u"Ignoring task '{0}' with {1} sub-tasks but doesn't have next task".format(name,
                                                                                                          child_count))
                continue
            if task['blocked'] and not child_count and not held:
                self.log.debug(u"Ignoring blocked task '{0}' with {1} sub-tasks and isn't a WF task".format(name,
                                                                                                            child_count))
                continue

            tasks[_id] = self.init_task(task)

        self.log.debug("Found {0} flagged tasks".format(len(tasks)))
        return tasks

    @staticmethod
    def task_from_row(row):
        name = row['name']
        blocked = row['blocked']
        child_count = row['childrenCount']
        has_next_task = row['containsNextTask']
        identifier = row['persistentIdentifier']
        tag = row['tag']
        note = row['plainTextNote']
        completed_date = row['dateCompleted']
        is_wf_task = name.startswith('WF')
        start_date = row['dateToStart']

        return dict(name=name, blocked=blocked, child_count=child_count, has_next_task=has_next_task,
                    start_date=start_date, identifier=identifier, tag=tag, note=note,
                    completed_date=completed_date, is_wf_task=is_wf_task)

    def close_tasks(self, identifiers):
        tasks_closed = []
        repeating_tasks_closed = []
        for identifier in identifiers:
            _id = identifier["id"]
            name = identifier["name"]

            close_task_result = self.close_task(_id, name)

            if close_task_result == 1:
                tasks_closed.append(identifier)
            elif close_task_result == 2:
                repeating_tasks_closed.append(identifier)

        return tasks_closed, repeating_tasks_closed

    def close_task(self, _id, name):
        try:
            of_task_name, rep_rule = self.get_task_details(_id)
            already_closed = Omnifocus.task_completed(_id)

            if already_closed:
                self.log.debug(u"Ignoring {0}{1} ({2}), already completed in Omnifocus".format(URI_PREFIX, _id, name))
                return 0

            if name != of_task_name:
                self.log.debug(
                    u"Ignoring {0}{1} ({2}), names don't match ({3})".format(URI_PREFIX, _id, name, of_task_name))
                return 0

            rep_type = 1

            if rep_rule is None:
                self.log.debug(u"Closing {0}{1} ({2})".format(URI_PREFIX, _id, name))
            else:
                self.log.debug(u"Closing repeating task {0}{1} ({2})".format(URI_PREFIX, _id, name))
                rep_type = 2

            scpt = applescript.AppleScript(CLOSE_TASK)
            scpt.call('close_task', _id)

            return rep_type
        except ValueError as e:
            self.log.debug(u"Ignoring {0}{1} ({2}), not found in Omnifocus".format(URI_PREFIX, _id, name))
            self.log.debug(e)
            return 0

    def get_task_details(self, _id):
        query = "SELECT * FROM Task WHERE persistentIdentifier = '{0}'".format(_id)
        cursor = self.conn.cursor()
        cursor.execute(query)
        result = cursor.fetchone()

        if result is None:
            raise ValueError("{0} not found in Omnifocus".format(_id))

        name = result["name"]
        rep_rule = result["repetitionMethodString"]
        return name, rep_rule

    def init_task(self, task):
        completed = None

        if task['completed_date']:
            completed = True

        _id = task['identifier']
        child_count = task['child_count']

        task_dict = dict(identifier=_id, name=task['name'], type=task['tag'], note=task['note'], completed=completed,
                         uri="{0}{1}".format(URI_PREFIX, _id))

        if child_count:
            child_tasks = []
            cursor = self.conn.cursor()
            cursor.execute(CHILD_TASKS_SQL.format(_id))
            results = cursor.fetchall()
            print "Found {0} child tasks".format(len(results))
            cursor.close()
            for child in results:
                child_tasks.append(self.init_task(Omnifocus.task_from_row(child)))

            task_dict['children'] = child_tasks

        logging.debug("Created task {0}".format(task_dict))
        return task_dict

    @staticmethod
    def task_completed(identifier):
        return applescript.AppleScript(IS_TASK_COMPLETE).call('task_completed', identifier)

    @staticmethod
    def deferred_date(date_to_start):
        date = None
        if date_to_start is not None:
            if date_to_start[-1:] != "Z":
                date_to_start = date_to_start + "Z"
            logging.debug("Determining task's deferred date: {0}".format(date_to_start))
            date = datetime.strptime(date_to_start, DATETIME_FORMAT)
        return date

    @staticmethod
    def is_deferred(date_to_start):
        now = datetime.now()
        logging.debug("Checking if task is deferred based on date_to_start {0} > {1}".format(date_to_start, now))
        deferred = False
        if date_to_start is not None and Omnifocus.deferred_date(date_to_start) > now:
            deferred = True
        return deferred


if __name__ == '__main__':
    omnifocus = Omnifocus()
    print omnifocus.get_task_details("k83Obd03UWV")
