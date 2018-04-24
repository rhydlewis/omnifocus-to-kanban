# Based heavily on this: https://github.com/msabramo/PyOmniFocus

import applescript
import logging
import os
import re
from datetime import datetime

from sqlalchemy import Column, Integer, Text, ForeignKey, or_, create_engine
from sqlalchemy.orm import relationship, backref, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

DB_LOCATION = ("/Library/Containers/com.omnigroup.OmniFocus2/"
               "Data/Library/Caches/com.omnigroup.OmniFocus2/OmniFocusDatabase2")
DB_PREFIX = ''
URI_PREFIX = 'omnifocus:///task/'
OFFSET = 978307200
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

Base = declarative_base()


class Omnifocus:
    log = logging.getLogger(__name__)

    def __init__(self):
        of_location = "{0}{1}".format(os.path.expanduser("~"), DB_LOCATION)
        if not os.path.isfile(of_location):
            of_location = re.sub(".OmniFocus2", ".OmniFocus2.MacAppStore", of_location)
        self.log.debug("Using Omnifocus location {0}".format(of_location))

        self.engine = create_engine('sqlite:///' + of_location, echo=False)
        self.session = sessionmaker()(bind=self.engine)

    def flagged_tasks(self):
        self.log.debug("Looking for flagged tasks")

        tasks = dict()

        results = self.session.query(Task).join(ProjectInfo). \
            filter(or_(Task.flagged == 1), Task.effectiveFlagged == 1). \
            filter(Task.dateCompleted.is_(None)). \
            filter(Task.blockedByFutureStartDate.is_(0)). \
            filter(ProjectInfo.status.notin_(['done', 'dropped', 'inactive'])). \
            order_by(Task.name)

        for task in results:
            name = task.task_name()
            blocked = task.blocked
            child_count = task.childrenCount
            has_next_task = task.containsNextTask
            is_wf_task = name.startswith('WF')

            if task.is_deferred():
                self.log.debug("Ignoring deferred task '{0}'".format(name))
                # print("Ignoring deferred task '{0}'".format(name))
                continue
            if (child_count and not has_next_task) and (child_count and not is_wf_task):
                self.log.debug("Ignoring task '{0}' with {1} sub-tasks but doesn't have next task {2}".format(
                    name, child_count, has_next_task))
                # print("Ignoring task '{0}' with {1} sub-tasks but doesn't have next task {2}".format(
                #     name, child_count, has_next_task))
                continue
            if blocked and not child_count and not is_wf_task:
                self.log.debug("Ignoring blocked task '{0}' with {1} sub-tasks and isn't a WF task".format(
                    name, child_count, is_wf_task))
                # print("Ignoring blocked task '{0}' with {1} sub-tasks and isn't a WF task".format(
                #     name, child_count, is_wf_task))
                continue

            # print "{0} {1} {2} {3}".format(task.task_name(), task.childrenCount, task.blocked, task.is_deferred())
            identifier = task.persistentIdentifier
            tasks[identifier] = Omnifocus.init_task(task)

        self.log.debug("Found {0} flagged tasks".format(len(tasks)))
        return tasks

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
            return 0

    def get_task_details(self, _id):
        result = self.session.query(Task).filter(Task.persistentIdentifier.is_(_id)).first()

        if result is None:
            raise ValueError("{0} not found in Omnifocus".format(_id))

        name = result.name
        rep_rule = result.repetitionMethodString
        return name, rep_rule


    @staticmethod
    def init_task(task):
        completed = None

        if task.dateCompleted:
            completed = True

        task_dict = dict(identifier=task.persistentIdentifier, name=task.task_name(),
                         type=task.context_name(), note=task.note, completed=completed,
                         uri="{0}{1}".format(URI_PREFIX, task.persistentIdentifier))

        if task.children:
            child_tasks = []
            for child_task in task.children:
                child_tasks.append(Omnifocus.init_task(child_task))

            task_dict['children'] = child_tasks

        logging.debug("Created task {0}".format(task_dict))

        return task_dict

    @staticmethod
    def task_completed(identifier):
        return applescript.AppleScript(IS_TASK_COMPLETE).call('task_completed', identifier)



class ProjectInfo(Base):
    __tablename__ = DB_PREFIX + 'ProjectInfo'

    pk = Column(Text, primary_key=True)
    task = Column(Text)
    status = Column(Text)


class Context(Base):
    __tablename__ = DB_PREFIX + 'Context'

    persistentIdentifier = Column(Text, primary_key=True)
    name = Column(Text)
    tasks = relationship('Task')


class Task(Base):
    __tablename__ = DB_PREFIX + 'Task'

    persistentIdentifier = Column(Text, primary_key=True)
    blocked = Column(Integer)
    blockedByFutureStartDate = Column(Integer)
    context = relationship('Context', backref=backref('Task'))
    flagged = Column(Integer)
    effectiveFlagged = Column(Integer)

    dateCompleted = Column(Integer)
    dateDue = Column(Integer)
    dateToStart = Column(Integer)
    effectiveDateToStart = Column(Integer)
    childrenCount = Column(Integer)

    note = Column('plainTextNote', Text)

    name = Column(Text)
    context_id = Column('context', Text, ForeignKey('Context.persistentIdentifier'))
    project_info = Column('containingProjectInfo', Text, ForeignKey('ProjectInfo.task'))
    parent_id = Column('parent', Text, ForeignKey('Task.persistentIdentifier'))

    children = relationship('Task', primaryjoin='Task.persistentIdentifier == Task.parent_id')

    repetitionMethodString = Column(Text)

    containsNextTask = Column(Integer)

    def __repr__(self):
        return self.name

    def deferred_date(self):
        date = None
        if self.dateToStart is not None:
            date = datetime.fromtimestamp(self.dateToStart + OFFSET)
        return date

    def is_complete(self):
        return self.dateCompleted is not None

    def is_deferred(self):
        deferred = False
        if self.dateToStart is not None:
            if self.deferred_date() > datetime.now():
                deferred = True

        return deferred

    def task_name(self):
        return self.name#.encode(ENCODING)

    def context_name(self):
        return self.context.name if self.context else 'None'


if __name__ == '__main__':
    omnifocus = Omnifocus()
    print omnifocus.flagged_tasks()