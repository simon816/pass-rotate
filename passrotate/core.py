import abc
import json
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .exceptions import AbortFlowException, RetryFlowException, \
     PassRotateException, RestartStageException

class Env:

    def __init__(self, provider, vars={}):
        self.__provider = provider
        self.__session = None
        self.__curr_resp = None
        self.__prev_resp = None
        self.__curr_url = None
        self.__doc = None
        self.__json = None
        self.__variables = dict(vars)

    @property
    def provider(self):
        return self.__provider

    @property
    def session(self):
        if self.__session is None:
            self.__session = requests.session()
        return self.__session

    @property
    def curr_resp(self):
        assert self.__curr_resp is not None, "No current response!"
        return self.__curr_resp

    @property
    def prev_resp(self):
        return self.__prev_resp

    @curr_resp.setter
    def curr_resp(self, resp):
        assert resp is not None, "Cannot set response to None"
        self.__prev_resp = self.__curr_resp
        self.__curr_resp = resp
        self.__curr_url = None
        self.__doc = None
        self.__json = None

    @property
    def curr_url(self):
        if self.__curr_url is None:
            self.__curr_url = urlparse(self.curr_resp.url)
        return self.__curr_url

    @property
    def document(self):
        if self.__doc is None:
            self.__doc = BeautifulSoup(self.curr_resp.text, "html5lib")
        return self.__doc

    @property
    def resp_json(self):
        if self.__json is None:
            self.__json = json.loads(self.curr_resp.text)
        return self.__json

    @property
    def vars(self):
        return self.__variables

class WriteVar:

    def __init__(self, name):
        self.path = name.split('.')

    def store(self, env, value):
        dict = env.vars
        for part in self.path[:-1]:
            if part not in dict:
                dict[part] = {}
            dict = dict[part]
        dict[self.path[-1]] = value

class Getter(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def get(self, env):
        pass

class Formatted(Getter):

    def __init__(self, string):
        self.str = string

    def get(self, env):
        try:
            return self.str.format(**env.vars)
        except Exception:
            raise Exception("Error in format string %r" % self.str)

    def __str__(self):
        return self.str

class TOTPPrompter(Getter):

    def get(self, env):
        from .provider import PromptType
        return env.provider.prompt("Enter your two factor (TOTP) code",
                                   PromptType.totp)

class SMSPrompter(Getter):

    def get(self, env):
        from .provider import PromptType
        return env.provider.prompt("Enter your SMS authorization code",
                                   PromptType.sms)

class GenericPrompter(Getter):

    def get(self, env):
        from .provider import PromptType
        return env.provider.prompt("Enter the challenge response",
                                   PromptType.generic)

class CAPTCHAPrompter(Getter):

    def get(self, env):
        from .provider import PromptType
        msg = ("The page at %s requires a CAPTCHA to be completed. " \
               "Please open the page, complete the CAPTCHA and paste " \
               "the response data (e.g. g-recaptcha-response for reCAPTCHA)"
               ) % (env.curr_resp.url)
        return env.provider.prompt(msg, PromptType.generic)

class Component(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def execute(self, env):
        pass

class Flow:

    def __init__(self, components):
        self.components = list(components)

    def run(self, env):
        for component in self.components:
            try:
                component.execute(env)
            except AbortFlowException:
                return
            except RetryFlowException:
                self.run(env)
                return
            except RestartStageException:
                raise # Bubble this exception
            except:
                raise PassRotateException("Error in component %s" % component)
