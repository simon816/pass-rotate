import json
import re
from urllib.parse import urljoin, urlparse, urlunparse

from .core import Component, Formatted, WriteVar, TOTPPrompter, SMSPrompter, \
     GenericPrompter, CAPTCHAPrompter
from .exceptions import AbortFlowException, RetryFlowException, \
     PassRotateException, RestartStageException
from .forms import get_form_data
from .util import ResponseMatcher, SuccessMatcher, exclusive

prompter = {
    'TOTP': TOTPPrompter(),
    'SMS': SMSPrompter(),
    'GENERIC': GenericPrompter(),
    'CAPTCHA': CAPTCHAPrompter(),
}

class URLSpec:

    def __init__(self, urlspec):
        if type(urlspec) == str:
            self.url_str = Formatted(urlspec)
        else:
            # TODO support building URL from individual components
            assert False, "TODO"

    def resolve(self, env):
        return self.url_str.get(env)

    def __str__(self):
        return str(self.url_str)

class IfMatchComponent(Component):

    def __init__(self, matchspec):
        self.matcher = ResponseMatcher(matchspec)

    def execute(self, env):
        match, err = self.matcher.match(env)
        if not match:
            raise AbortFlowException()

    def __str__(self):
        return 'if_match'

class PromptComponent(Component):

    def __init__(self, promptspec):
        self.prompter = prompter[promptspec['type']]
        self.var = WriteVar(promptspec['variable'])

    def execute(self, env):
        self.var.store(env, self.prompter.get(env))

    def __str__(self):
        return 'prompt'

class SetVariableComponent(Component):

    def __init__(self, varspec):
        self.var = WriteVar(varspec['variable'])
        self.val = Formatted(varspec['value'])

    def execute(self, env):
        self.var.store(env, self.val.get(env))

    def __str__(self):
        return 'set_variable'

class SetCookieComponent(Component):

    def __init__(self, cookies):
        self.cookies = [
            { key: Formatted(val) for key, val in cookie.items() } \
            for cookie in cookies
        ]

    def execute(self, env):
        for cookie in self.cookies:
            name = cookie['name'].get(env)
            value = cookie['value'].get(env)
            kwargs = {
                key: var.get(env) for key, var in cookie.items() \
                if key not in ['name', 'value']
            }
            env.session.cookies.set(name, value, **kwargs)

    def __str__(self):
        return 'set_cookie'

class GetURLComponent(Component):

    def __init__(self, args):
        self.follow_redirects = True
        self.headers = {}
        # Short-cut for basic string urls
        if type(args) == str:
            urlspec = args
        else:
            urlspec = args['url']
            self.follow_redirects = 'follow_redirects' not in args \
                                    or args['follow_redirects']
        self.url = URLSpec(urlspec)
        if 'headers' in args:
            self.headers = {
                name: Formatted(var) for name, var in args['headers'].items()
            }

    def execute(self, env):
        headers = {
            name: var.get(env) for name, var in self.headers.items()
        }
        env.curr_resp = env.session.get(self.url.resolve(env),
                allow_redirects=self.follow_redirects, headers=headers)
        SuccessMatcher.DEFAULT.check(env)

    def __str__(self):
        return 'get_url %s' % self.url

class StoreJSJSONComponent(Component):

    def __init__(self, spec):
        self.re = re.compile(spec['match'])
        self.var = WriteVar(spec['variable'])

    def execute(self, env):
        for script in env.document.find_all("script"):
            match = self.re.match(script.text)
            if match:
                data = json.loads(match.group(1))
                self.var.store(env, data)
                return
        raise PassRotateException("Could not find match %s" % self.re)

    def __str__(self):
        return 'store_js_json, match: %s' % self.re

class FormMatcher:

    def __init__(self, formspec):
        self.fields = []
        self.fill_map = {}
        self.attr_map = {}
        self.value_map = {}
        for match in formspec:
            assert exclusive(match, 'field', 'attr')
            if 'field' in match:
                fname = match['field']
                assert exclusive(match, 'fill', 'prompt')
                self.fields.append(fname)
                if 'value' in match:
                    self.value_map[fname] = Formatted(match['value'])
                if 'fill' in match:
                    var = Formatted(match['fill'])
                elif 'prompt' in match:
                    var = prompter[match['prompt']]
                else:
                    continue
                self.fill_map[fname] = var
            elif 'attr' in match:
                self.attr_map[match['attr']] = Formatted(match['value'])
            else:
                assert False, "Form match must have 'field' or 'attr'"

    def match(self, env):
        attrs = {
            name: var.get(env) for name, var in self.attr_map.items()
        }
        for form in env.document.find_all('form', attrs=attrs):
            inputs = form.find_all('input') + form.find_all('select')
            form_data = get_form_data(inputs)
            # If all required fields are present and required values match
            if all(field in form_data for field in self.fields) \
                and all(form_data[name] == var.get(env) \
                    for name, var in self.value_map.items()):
                for field, variable in self.fill_map.items():
                    form_data[field] = variable.get(env)
                return {
                    'action': form.get('action'),
                    'method': form.get('method').upper(),
                    'data': form_data,
                }
        return None

    def __str__(self):
        return "form with fields %s" % self.fields

class MatchFormComponent(Component):

    def __init__(self, formspec):
        self.matcher = FormMatcher(formspec)

    def execute(self, env):
        form = self.matcher.match(env)
        if form is None:
            raise PassRotateException("Coud not find form matching %s" % \
                                  self.matcher)
        env.form = form

    def __str__(self):
        return 'match_form'

class MatchAnyFormComponent(Component):

    def __init__(self, formspecs):
        self.matchers = [FormMatcher(formspec) for formspec in formspecs]

    def execute(self, env):
        for matcher in self.matchers:
            form = matcher.match(env)
            if form is not None:
                env.form = form
                return
        raise PassRotateException("Could not find any forms matching " \
                                  + ', '.join(map(str, self.matchers)))

    def __str__(self):
        return 'match_any_form'

class StoreElementComponent(Component):

    def __init__(self, elemspec):
        self.elem_name = elemspec['element']
        self.attr_match = {}
        if 'attrs' in elemspec:
            self.attr_match = {
                attr: Formatted(val) for attr, val in elemspec['attrs'].items()
            }
        storespec = elemspec['store']
        assert exclusive(storespec, 'attr', 'text')
        if 'attr' in storespec:
            self.storer = self.store_attr(storespec['attr'])
        elif 'text' in storespec:
            self.storer = self.store_text(re.compile(storespec['text']))
        else:
            assert False
        self.variable = WriteVar(storespec['variable'])

    def execute(self, env):
        attrs = {
            name: var.get(env) for name, var in self.attr_match.items()
        }
        elem = env.document.find(self.elem_name, attrs=attrs)
        if elem is None:
            raise PassRotateException("Cannot find <%s> element with attrs %s" \
                                      % (self.elem_name, attrs))
        val = self.storer(elem)
        self.variable.store(env, val)

    def store_attr(self, attrname):
        def get(elem):
            val = elem.get(attrname)
            if val is None:
                raise PassRotateException("Element doesn't have attribute %s" \
                                          % attrname)
            return val
        return get

    def store_text(self, regex):
        def match(elem):
            m = regex.search(elem.text)
            if m is None:
                raise PassRotateException("No match for %s" % regex)
            return m.group(1)
        return match

    def __str__(self):
        return 'store_element'

class StoreURLComponent(Component):

    def __init__(self, storespec):
        self.part_map = {}
        for part, store in storespec.items():
            if type(store) == str:
                handler = self.store_var
                var = store
            else:
                handler = self.from_regex(re.compile(store['match']))
                var = store['variable']
            self.part_map[part] = (handler, WriteVar(var))

    def execute(self, env):
        url = env.curr_url
        for part, (handler, var) in self.part_map.items():
            var.store(env, handler(getattr(url, part)))

    def store_var(self, value):
        return value

    def from_regex(self, regex):
        def store(value):
            match = regex.search(value)
            if match is None:
                raise PassRotateException("No match on %s" % regex)
            return match.group(1)
        return store

    def __str__(self):
        return 'store_url'

class StoreJSONComponent(Component):

    def __init__(self, variable):
        self.variable = WriteVar(variable)

    def execute(self, env):
        self.variable.store(env, env.resp_json)

    def __str__(self):
        return 'store_json'

class StoreCookieComponent(Component):

    def __init__(self, storespec):
        self.store_map = {
            name: WriteVar(var) for name, var in storespec.items()
        }

    def execute(self, env):
        for name, var in self.store_map.items():
            cookie = env.session.cookies.get(name)
            if cookie is None:
                raise PassRotateException("No such cookie %s" % name)
            var.store(env, cookie)

    def __str__(self):
        return 'store_cookie'

class ActionHandler(Component):

    def __init__(self, args):
        self.success_match = SuccessMatcher.DEFAULT
        self.fail_mode = 'die'
        if 'success' in args:
            self.success_match = SuccessMatcher(args['success'])
        if 'fail' in args:
            self.fail_mode = args['fail']
        assert self.fail_mode in ('die', 'retry', 'restart')

    def execute(self, env):
        try:
            self.exec_action(env)
            if self.success_match is not None:
                self.success_match.check(env)
        except Exception:
            if self.fail_mode == 'die':
                raise
            elif self.fail_mode == 'retry':
                raise RetryFlowException()
            elif self.fail_mode == 'restart':
                raise RestartStageException()

class SubmitFormAction(ActionHandler):

    def __init__(self, args):
        super().__init__(args)
        self.headers = {}
        self.follow_redirects = True
        if 'headers' in args:
            self.headers = {
                name: Formatted(var) for name, var in args['headers'].items()
            }
        if 'follow_redirects' in args:
            self.follow_redirects = args['follow_redirects']

    def exec_action(self, env):
        url = urljoin(env.curr_resp.url, env.form['action'])
        method = env.form['method']
        data = params = None
        if method == 'GET':
            params = env.form['data']
        else:
            data = env.form['data']
        headers = {
            name: var.get(env) for name, var in self.headers.items()
        }
        env.curr_resp = env.session.request(
            method, url, data=data, params=params, headers=headers,
            allow_redirects=self.follow_redirects)

    def __str__(self):
        return 'submit_form'

class DataHandler:

    def __init__(self, params):
        self.params = self.apply_recursive(lambda v: Formatted(str(v)), params)

    def apply_recursive(self, func, value):
        if type(value) == dict:
            return {
                key: self.apply_recursive(func, var) \
                    for key, var in value.items()
            }
        if type(value) == list:
            return [self.apply_recursive(func, var) for var in value]
        return func(value)

    def resolve(self, env):
        return self.apply_recursive(lambda v: v.get(env), self.params)

class FormDataHandler(DataHandler):

    def to_data(self, env):
        return self.resolve(env)

class JsonDataHandler(DataHandler):

    def to_data(self, env):
        return json.dumps(self.resolve(env))

class HTTPVerbAction(ActionHandler):

    def __init__(self, verb, args):
        super().__init__(args)
        self.verb = verb
        self.url = URLSpec(args['url'])
        self.data_handler = None
        self.headers = {}
        self.follow_redirects = True

        assert exclusive(args, 'data', 'data_json')
        if 'data' in args:
            self.data_handler = FormDataHandler(args['data'])
        if 'data_json' in args:
            self.data_handler = JsonDataHandler(args['data_json'])
        if 'headers' in args:
            self.headers = {
                name: Formatted(var) for name, var in args['headers'].items()
            }
        if 'follow_redirects' in args:
            self.follow_redirects = args['follow_redirects']

    def exec_action(self, env):
        data = None
        if self.data_handler:
            data = self.data_handler.to_data(env)
        headers = {
            name: var.get(env) for name, var in self.headers.items()
        }
        url = self.url.resolve(env)
        env.curr_resp = env.session.request(
            self.verb, url, data=data, headers=headers,
            allow_redirects=self.follow_redirects)

    def __str__(self):
        return 'http_%s, URL: %s' % (self.verb.lower(), self.url)

def HTTPAction(verb):
    def ctor(args):
        return HTTPVerbAction(verb, args)
    return ctor

action_components = {
    'submit_form': SubmitFormAction,
    'http_post': HTTPAction('POST'),
    'http_put': HTTPAction('PUT'),
    'http_patch': HTTPAction('PATCH'),
    'http_get': HTTPAction('GET'),
}

def ActionComponent(spec):
    if type(spec) == str:
        action = spec
        args = {}
    else:
        action = spec['type']
        args = spec
    return action_components[action](args)

component_map = {
    'if_match': IfMatchComponent,
    'prompt': PromptComponent,
    'set_variable': SetVariableComponent,
    'set_cookie': SetCookieComponent,
    'get_url': GetURLComponent,
    'store_js_json': StoreJSJSONComponent,
    'store_url': StoreURLComponent,
    'store_cookie': StoreCookieComponent,
    'store_element': StoreElementComponent,
    'store_json': StoreJSONComponent,
    'match_form': MatchFormComponent,
    'match_any_form': MatchAnyFormComponent,
    'action': ActionComponent,
}

# Components will always be executed in the following order
component_ordering = (
    IfMatchComponent,
    PromptComponent,
    SetVariableComponent,
    SetCookieComponent,
    GetURLComponent,
    StoreJSJSONComponent,
    StoreURLComponent,
    StoreCookieComponent,
    StoreElementComponent,
    StoreJSONComponent,
    MatchFormComponent,
    MatchAnyFormComponent,
    ActionComponent,
)
