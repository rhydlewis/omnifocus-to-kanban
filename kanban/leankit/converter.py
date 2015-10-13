import re


class Converter(object):
    """Convert JSON returned by Leankit to Python classes.

    JSON returned by Leankit is in the form of a dict with CamelCase
    named values which are converted to lowercase underscore-separated
    class attributes.

    Any required attributes are defined in attribute 'attributes',
    and optional ones in 'optional_attributes' using the originating
    key names (CamelCase).  Optional values will be set to None if
    they are not defined.

    Whenever any of required or optional attributes are modified,
    is_dirty will be set to True and dirty_attrs will contain a set
    of modified attributes.
    """
    attributes = []
    optional_attributes = []

    def direct_setattr(self, attr, value):
        super(Converter, self).__setattr__(attr, value)

    def __init__(self, raw_data):
        self.direct_setattr('is_dirty', False)
        self.direct_setattr('dirty_attrs', set([]))
        self.direct_setattr('_raw_data', raw_data)
        self.direct_setattr('_watched_attrs', set([]))

        for attr in self.attributes:
            attr_name = self._prettify_name(attr)
            self._watched_attrs.add(attr_name)
            self.direct_setattr(attr_name, raw_data[attr])

        for attr in self.optional_attributes:
            attr_name = self._prettify_name(attr)
            self._watched_attrs.add(attr_name)
            self.direct_setattr(attr_name, raw_data.get(attr, None))

    def _prettify_name(self, camelcase):
        camelcase = camelcase.replace('ID', '_id')
        if len(camelcase) > 1:
            repl_func = lambda match: '_' + match.group(1).lower()
            camelcase = camelcase[0].lower() + camelcase[1:]
            return re.sub('([A-Z])', repl_func, camelcase)
        else:
            return camelcase.lower()

    def _to_camel_case(self, name):
        if len(name) > 1:
            repl_func = lambda match: match.group(1)[1:].upper()
            name = name[0].upper() + name[1:]
            return re.sub('(_[a-z])', repl_func, name)
        else:
            return name.upper()

    def __setattr__(self, attr, value):
        if (not hasattr(self, attr) or getattr(self, attr, None) != value) \
                and attr in self._watched_attrs:
            self.direct_setattr('is_dirty', True)
            self.dirty_attrs.add(attr)
        self.direct_setattr(attr, value)