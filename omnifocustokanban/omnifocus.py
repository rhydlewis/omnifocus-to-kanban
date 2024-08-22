# Based heavily on this: https://github.com/msabramo/PyOmniFocus

import applescript
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

class TaskStatus(Enum):
    DONE = 'done'
    DROPPED = 'dropped'
    INACTIVE = 'inactive'


# DB_LOCATION = "/Library/Group Containers/34YW5XSRB7.com.omnigroup.OmniFocus/com.omnigroup.OmniFocus3/" \
#               "com.omnigroup.OmniFocusModel/OmniFocusDatabase.db"

DB_LOCATION = "/Library/Group Containers/34YW5XSRB7.com.omnigroup.OmniFocus/com.omnigroup.OmniFocus4/" \
              "com.omnigroup.OmniFocusModel/OmniFocusDatabase.db"
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

# SQL queries as constants
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
  AND ProjectInfo.status NOT IN (?, ?, ?)
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
  AND ProjectInfo.status NOT IN (?, ?, ?)
  AND Task.parent = ?
"""


class Omnifocus:
    log = logging.getLogger(__name__)

    def __init__(self):
        self.of_location = f"{os.path.expanduser('~')}{DB_LOCATION}"
        if not os.path.isfile(self.of_location):
            self.of_location = re.sub(".OmniFocus3", ".OmniFocus3.MacAppStore", self.of_location)
        self.log.debug(f"Using Omnifocus location {self.of_location}")

        try:
            self.conn = sqlite3.connect(self.of_location)
            self.conn.row_factory = sqlite3.Row
        except sqlite3.Error as e:
            self.log.error(f"Error connecting to database: {e}")
            raise

    def flagged_tasks(self) -> Dict[str, Task]:
        self.log.debug("Looking for flagged tasks")

        tasks = {}

        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(FLAGGED_TASKS_SQL, (TaskStatus.DONE.value, TaskStatus.DROPPED.value, TaskStatus.INACTIVE.value))
                results = cursor.fetchall()
                self.log.debug(f"Found {len(results)} results")

            for row in results:
                task = self.task_from_row(row)
                child_count = task['child_count']
                name = task['name']
                held = task['is_wf_task']
                _id = task['identifier']
                start_date = task['start_date']  # timestamp in OmniFocus 3.6

                if self.is_deferred(start_date):
                    self.log.debug(f"Ignoring deferred task '{name}'")
                    continue
                if (child_count and not task['has_next_task']) and (child_count and not held):
                    self.log.debug(f"Ignoring task '{name}' with {child_count} sub-tasks but doesn't have next task")
                    continue
                if task['blocked'] and not child_count and not held:
                    self.log.debug(f"Ignoring blocked task '{name}' ({child_count} sub-tasks) that isn't a WF task")
                    continue

                tasks[_id] = self.init_task(task)

            self.log.debug(f"Found {len(tasks)} flagged tasks")
            return tasks
        except sqlite3.Error as e:
            self.log.error(f"Database error: {e}")
            raise

    @staticmethod
    def task_from_row(row: sqlite3.Row) -> Dict[str, Any]:
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

        return {
            'name': name,
            'blocked': blocked,
            'child_count': child_count,
            'has_next_task': has_next_task,
            'start_date': start_date,
            'identifier': identifier,
            'tag': tag,
            'note': note,
            'completed_date': completed_date,
            'is_wf_task': is_wf_task
        }

    def close_tasks(self, identifiers: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
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

    def close_task(self, _id: str, name: str) -> int:
        try:
            of_task_name, rep_rule = self.get_task_details(_id)
            already_closed = self.task_completed(_id)

            if already_closed:
                self.log.debug(f"Ignoring {URI_PREFIX}{_id} ({name}), already completed in Omnifocus")
                return 0

            if name != of_task_name:
                self.log.debug(f"Ignoring {URI_PREFIX}{_id} ({name}), names don't match ({of_task_name})")
                return 0

            rep_type = 1

            if rep_rule is None:
                self.log.debug(f"Closing {URI_PREFIX}{_id} ({name})")
            else:
                self.log.debug(f"Closing repeating task {URI_PREFIX}{_id} ({name})")
                rep_type = 2

            scpt = applescript.AppleScript(CLOSE_TASK)
            scpt.call('close_task', _id)

            return rep_type
        except ValueError as e:
            self.log.debug(f"Ignoring {URI_PREFIX}{_id} ({name}), not found in Omnifocus")
            self.log.debug(e)
            return 0

    def get_task_details(self, _id: str) -> Tuple[str, Optional[str]]:
        query = "SELECT * FROM Task WHERE persistentIdentifier = ?"
        try:
            with self.conn:
                cursor = self.conn.cursor()
                cursor.execute(query, (_id,))
                result = cursor.fetchone()

            if result is None:
                raise ValueError(f"{_id} not found in Omnifocus")

            name = result["name"]
            rep_rule = result["repetitionMethodString"]
            return name, rep_rule
        except sqlite3.Error as e:
            self.log.error(f"Database error: {e}")
            raise

    def init_task(self, task: Dict[str, Any]) -> Task:
        completed = None

        if task['completed_date']:
            completed = True

        _id = task['identifier']
        child_count = task['child_count']

        task_obj = Task(
            identifier=_id,
            name=task['name'],
            type=task['tag'],
            note=task['note'],
            completed=completed,
            uri=f"{URI_PREFIX}{_id}"
        )

        if child_count:
            child_tasks = []
            try:
                with self.conn:
                    cursor = self.conn.cursor()
                    cursor.execute(CHILD_TASKS_SQL, (TaskStatus.DONE.value, TaskStatus.DROPPED.value, TaskStatus.INACTIVE.value, _id))
                    results = cursor.fetchall()
                self.log.debug(f"Found {len(results)} child tasks")
                for child in results:
                    child_tasks.append(self.init_task(self.task_from_row(child)))

                task_obj.children = child_tasks
            except sqlite3.Error as e:
                self.log.error(f"Database error: {e}")
                raise

        self.log.debug(f"Created task {task_obj}")
        return task_obj

    @staticmethod
    def task_completed(identifier: str) -> bool:
        return applescript.AppleScript(IS_TASK_COMPLETE).call('task_completed', identifier)

    @staticmethod
    def deferred_date(date_to_start: Optional[str]) -> Optional[datetime]:
        if date_to_start is not None:
            if date_to_start[-1:] != "Z":
                date_to_start += "Z"
            logging.debug(f"Determining task's deferred date: {date_to_start}")
            return datetime.strptime(date_to_start, DATETIME_FORMAT)
        return None

    @staticmethod
    def is_deferred(date_to_start: Optional[str]) -> bool:
        now = datetime.now(timezone.utc)
        logging.debug(f"Checking if task is deferred based on date_to_start {date_to_start} > {now}")
        if date_to_start is not None:
            deferred_date = Omnifocus.deferred_date(date_to_start)
            return deferred_date is not None and deferred_date.replace(tzinfo=timezone.utc) > now
        return False


if __name__ == '__main__':
    omnifocus = Omnifocus()
    print(omnifocus.get_task_details("k83Obd03UWV"))
@dataclass
class Task:
    identifier: str
    name: str
    type: str
    note: str
    completed: Optional[bool]
    uri: str
    children: Optional[List['Task']] = None
