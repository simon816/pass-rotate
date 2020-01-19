import yaml
import glob
import os

from .core import Flow
from .components import component_map, component_ordering
from .provider import FlowProvider, ProviderOption, register_provider

def build_flow(spec):
    # create slots to place components in correct order
    # Not the most optimal sorting algo but it'll do
    ordered = [None] * len(component_ordering)

    for key, value in spec.items():
        component_cls = component_map[key]
        idx = component_ordering.index(component_cls)
        instance = component_cls(value)
        # Place component in correct slot
        ordered[idx] = instance

    # Filter out empty slots
    components = [c for c in ordered if c is not None]
    return Flow(components)

def make_option(optspec):
    # Simple string option - optspec is the description
    if type(optspec) == str:
        return ProviderOption(str, optspec)
    # Otherwise, create from dictionary
    if type(optspec) == dict:
        opttype = optspec['values'] if 'values' in optspec else str
        return ProviderOption(opttype, optspec['description'],
                              'optional' in optspec and optspec['optional'])
    assert False

def make_provider(spec):
    prepare_flows = []
    if 'prepare' in spec:
        prepare_flows = [build_flow(flowspec) for flowspec in spec['prepare']]
    execute_flows = [build_flow(flowspec) for flowspec in spec['execute']]

    opts = spec['options'] if 'options' in spec else {}
    _options = {
        key: make_option(optspec) for key, optspec in opts.items()
    }

    opt_desc = '\n'.join('    %s=%s' % itm for itm in sorted(_options.items()))
    doc = "    [%s]\n%s" % (spec['domains'][0], opt_desc)

    class YAMLProvider(FlowProvider):
        __doc__ = doc

        name = spec['name']
        domains = spec['domains']
        options = _options

        def __init__(self, options):
            self.__options = options

        def get_init_variables(self):
            return self.__options

        def get_prepare_flows(self, old_password):
            return prepare_flows

        def get_execute_flows(self, old_password, new_password):
            return execute_flows

    return YAMLProvider

for path in glob.glob(
    os.path.join(os.path.dirname(__file__), 'providers', '*.yaml')):
    with open(path, 'r') as f:
        try:
            spec = yaml.safe_load(f)
            register_provider(make_provider(spec))
        except:
            raise Exception("Error while building provider at %s" % path)
