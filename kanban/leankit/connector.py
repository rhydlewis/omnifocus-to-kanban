import requests
import json
import logging

# Leankit response codes
NO_DATA = 100
DATA_RETRIEVAL_SUCCESS = 200
DATA_INSERT_SUCCESS = 201
DATA_UPDATE_SUCCESS = 202
DATA_DELETE_SUCCESS = 203
SYSTEM_EXCEPTION = 500
MINOR_EXCEPTION = 501
USER_EXCEPTION = 502
FATAL_EXCEPTION = 503
THROTTLE_WAIT_RESPONSE = 800
WIP_OVERRIDE_COMMENT_REQUIRED = 900
RESENDING_EMAIL_REQUIRED = 902
UNAUTHORIZED_ACCESS = 1000
SUCCESS_CODES = [DATA_RETRIEVAL_SUCCESS, DATA_INSERT_SUCCESS, DATA_UPDATE_SUCCESS,
                 DATA_DELETE_SUCCESS]

log = logging.getLogger(__name__)


class LeankitConnector(object):
    def __init__(self, account, username=None, password=None):
        host = 'https://' + account + '.leankitkanban.com'
        self.base_api_url = host + '/Kanban/Api'
        self.http = LeankitConnector.configure_auth(username, password)

    @staticmethod
    def configure_auth(username=None, password=None):
        """Configure the http object to use basic auth headers."""
        http = requests.sessions.Session()
        if username is not None and password is not None:
            http.auth = (username, password)
        return http

    def post(self, url, data, handle_errors=True):
        data = json.dumps(data)
        log.debug("> POST {0} {1}".format(self.base_api_url + url, data))
        return self._do_request("POST", url, data, handle_errors)

    def get(self, url, handle_errors=True):
        log.debug("< GET {0}".format(self.base_api_url + url))
        return self._do_request("GET", url, None, handle_errors)

    def _do_request(self, action, url, data=None, handle_errors=True):
        """Make an HTTP request to the given url possibly POSTing some data."""
        assert self.http is not None, "HTTP connection should not be None"
        headers = {'Content-type': 'application/json'}

        try:
            resp = self.http.request(method=action, url=self.base_api_url + url, data=data,
                                     auth=self.http.auth, headers=headers)
        except Exception as e:
            raise IOError("Unable to make HTTP request: {0}".format(e.message))

        if resp.status_code not in SUCCESS_CODES:
            log.error("Error from Lean Kit")
            log.error(resp)
            raise IOError("Leankit error {0}".format(resp.status_code))

        response = Record(json.loads(resp.content))

        if handle_errors and response.ReplyCode not in SUCCESS_CODES:
            raise IOError("Leankit error {0}: {1}".format(response.ReplyCode, response.ReplyText))
        return response


class Record(dict):
    """A little dict subclass that adds attribute access to values."""

    def __hash__(self):
        return hash(repr(self))

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(e)

    def __setattr__(self, name, value):
        self[name] = value
