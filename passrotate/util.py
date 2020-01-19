import re
from urllib.parse import urlparse

from .exceptions import PassRotateException

def matcher(key, type, desc):
    def decorator(func):
        func.match_key = key
        func.match_type = type
        func.desc = desc
        return func
    return decorator

class ResponseMatcher:

    _match_map = {}

    @classmethod
    def __class_init(cls):
        for name in dir(cls):
            attr = getattr(cls, name)
            if callable(attr) and hasattr(attr, 'match_key'):
                cls._match_map[attr.match_key] = attr

    def __init__(self, matchspec):
        if not self._match_map:
            self.__class_init()

        self.checks = []

        for key, val in matchspec.items():
            inverse = key.endswith('_not')
            if inverse:
                key = key[:-4]
            func = self._match_map[key]
            type = func.match_type
            if type == 'I':
                val = int(val)
            elif type == 'RE':
                val = re.compile(val)
            self.checks.append((func, val, inverse))

    def match(self, env):
        for (func, val, inverse) in self.checks:
            reason = func.desc
            result = func(val, env)
            if inverse:
                result = not result
                reason = "NOT " + reason
            if not result:
                return False, reason % val
        return True, None

    @matcher('status', 'I', "Status is %d")
    def match_status(want_status, env):
        return env.curr_resp.status_code == want_status

    @matcher('text_match', 'RE', "Text matches %s")
    def match_text(regex, env):
        return regex.search(env.curr_resp.text) is not None

    @matcher('path_match', 'RE', "Path matches %s")
    def match_path(regex, env):
        path = urlparse(env.curr_resp.url).path
        return regex.search(path) is not None

    @matcher('document', None, "Document contains elements %s")
    def match_document(elemlist, env):
        for elem in elemlist:
            attrs = elem['attrs'] if 'attrs' in elem else {}
            if env.document.find(elem['element'], **attrs) is None:
                return False
        return True

class SuccessMatcher(ResponseMatcher):

    DEFAULT = None

    def check(self, env):
        result, err = self.match(env)
        if not result:
            raise PassRotateException("Check failed: " + err)

SuccessMatcher.DEFAULT = SuccessMatcher({'status':200})

def exclusive(dict, *opts):
    for opt in opts:
        if opt in dict:
            return all(other not in dict for other in opts if other != opt)
    return True

def literal(str):
    return str.replace('{', '{{').replace('}', '}}')
