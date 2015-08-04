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

TASK_COMPLETE_SCRIPT = '''
        on task_completed(task_id)
            tell application "OmniFocus"
                try
                    set theTask to task id task_id of default document
                    return completed of theTask
                end try
            end tell
        end run
    '''
CLOSE_TASK_SCRIPT = '''
        on close_task(task_id)
            tell application "OmniFocus"
                set completed_task to task id task_id of default document
                set completed of completed_task to true
                return completed of completed_task
            end tell
        end run
    '''

Base = declarative_base()


class Omnifocus:
    log = logging.getLogger(__name__)

    def __init__(self):
        of_location = "{0}{1}".format(os.path.expanduser("~"), DB_LOCATION)
        if not os.path.isfile(of_location):
            of_location = re.sub(".OmniFocus2", ".OmniFocus2.MacAppStore", of_location)
        self.log.info("Using Omnifocus location {0}".format(of_location))

        self.engine = create_engine('sqlite:///' + of_location, echo=False)
        self.session = sessionmaker()(bind=self.engine)

    def flagged_tasks(self):
        self.log.debug("Looking for flagged tasks")

        tasks = []

        results = self.session.query(Task).join(ProjectInfo). \
            filter(or_(Task.flagged == 1), Task.effectiveFlagged == 1). \
            filter(Task.dateCompleted.is_(None)). \
            filter(ProjectInfo.status.notin_(['done', 'dropped', 'inactive'])). \
            order_by(Task.name)

        for task in results:
            if not task.is_deferred():
                tasks.append(dict(identifier=task.persistentIdentifier, name=task.task_name(),
                                  type=task.context_name()))

        self.log.debug("Found {0} flagged tasks".format(len(tasks)))
        return tasks

    def close_tasks(self, identifiers):
        for identifier in identifiers:
            self.close_task(identifier)

    def close_task(self, identifier):
        already_closed = Omnifocus.task_completed(identifier)
        if already_closed:
            self.log.debug("Ignoring {0}{1}, already completed in Omnifocus".format(URI_PREFIX, identifier))
        elif already_closed is not None:
            self.log.info("Closing {0}{1}".format(URI_PREFIX, identifier))
            scpt = applescript.AppleScript(CLOSE_TASK_SCRIPT)
            result = scpt.call('close_task', identifier)

            if not result:
                self.log.warn("Failed to close task {0}{1}".format(URI_PREFIX, identifier))
        else:
            self.log.warn("Failed to find task {0}{1}".format(URI_PREFIX, identifier))

    @staticmethod
    def task_completed(identifier):
        return applescript.AppleScript(TASK_COMPLETE_SCRIPT).call('task_completed', identifier)


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

    name = Column(Text)
    context_id = Column('context', Text, ForeignKey('Context.persistentIdentifier'))
    project_info = Column('containingProjectInfo', Text, ForeignKey('ProjectInfo.task'))
    parent_id = Column('parent', Text, ForeignKey('Task.persistentIdentifier'))

    children = relationship('Task', primaryjoin='Task.persistentIdentifier == Task.parent_id')

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
        return self.name.encode(ENCODING)

    def context_name(self):
        return self.context.name if self.context else 'None'
