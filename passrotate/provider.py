import abc
from enum import Enum

from .core import Env
from .exceptions import PassRotateException, RestartStageException

_providers = list()
_provider_map = dict()
_provider_domains = dict()

def register_provider(provider):
    _providers.append(provider)
    _provider_map[provider.name] = provider
    for d in provider.domains:
        _provider_domains[d] = provider

def get_provider(domain):
    return _provider_map.get(domain) or _provider_domains.get(domain)

def get_providers():
    return _providers

class PromptType(Enum):
    generic = "generic"
    totp = "totp"
    sms = "sms"

class ProviderOption:
    def __init__(self, type, doc, optional=False):
        self.type = type
        self.doc = doc
        self.optional = optional

    def __str__(self):
        values = ''
        optional = ''
        if type(self.type) == dict:
            values = ' (' + ', '.join(self.type.values()) + ')'
        if self.optional:
            optional = 'Optional, '
        return optional + self.doc + values

class Provider:

    def prompt(self, prompt, prompt_type):
        return self._prompt(prompt, prompt_type)

    @abc.abstractmethod
    def prepare(self, old_password):
        pass

    @abc.abstractmethod
    def execute(self, old_password, new_password):
        pass

class FlowProvider(Provider, metaclass=abc.ABCMeta):

    def get_init_variables(self):
        return {}

    def get_prepare_flows(self, old_password):
        return []

    @abc.abstractmethod
    def get_execute_flows(self, old_password, new_password):
        pass

    def prepare(self, old_password):
        self.env = Env(self, vars=dict(
            self.get_init_variables(),
            old_password = old_password,
        ))
        self.run_flows('prepare', self.get_prepare_flows(old_password))

    def execute(self, old_password, new_password):
        self.env.vars.update({
            'old_password': old_password,
            'new_password': new_password,
        })
        self.run_flows('execute',
                       self.get_execute_flows(old_password, new_password))

    def run_flows(self, stage, flows):
        flows = list(flows)
        for i, flow in enumerate(flows):
            try:
                flow.run(self.env)
            except RestartStageException:
                self.run_flows(stage, flows)
                return
            except Exception as e:
                raise PassRotateException("Error in %s stage, step %d" % (
                    stage, i + 1))
