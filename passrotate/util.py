import re
from urllib.parse import parse_qs

from .core import Formatted
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
            elif type == 'FSTR':
                val = Formatted(val)
            elif type == 'DICT_RE':
                val = { k: re.compile(v) for k, v in val.items() }
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
        path = env.curr_url.path
        return regex.search(path) is not None

    @matcher('query_match', 'DICT_RE', "Query matches %s")
    def match_query(querymatch, env):
        query = parse_qs(env.curr_url.query)
        for key, regex in querymatch.items():
            value = query.get(key, '')
            if not regex.search(value):
                return False
        return True

    @matcher('document', None, "Document contains elements %s")
    def match_document(elemlist, env):
        for elem in elemlist:
            attrs = elem['attrs'] if 'attrs' in elem else {}
            if env.document.find(elem['element'], **attrs) is None:
                return False
        return True

    @matcher('json', None, 'Response JSON matches %s')
    def match_json(expect, env):
        json = env.resp_json
        return match_json_recursive(expect, json)

    @matcher('variable_exists', 'FSTR', "Variable %s exists")
    def match_var_exists(var, env):
        try:
            return bool(var.get(env))
        except KeyError:
            return False

def match_json_recursive(expect, got):
    if type(expect) == dict:
        return match_json_object(expect, got)
    if type(expect) == list:
        return match_json_array(expect, got)
    if type(expect) != type(got):
        return False
    return expect == got

def match_json_object(expect, got):
    if type(got) != dict:
        return False
    for key, value in expect.items():
        if key not in got:
            return False
        got_val = got[key]
        if not match_json_recursive(value, got_val):
            return False
    return True

def match_json_array(expect, got):
    if type(got) != list:
        return False
    for item in expect:
        if not any(match_json_recursive(item, got_elem) for got_elem in got):
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
