# Contributing

To get help, visit [#cmpwn on irc.freenode.net](http://webchat.freenode.net/?channels=cmpwn&uio=d4).

## Adding new password managers

If you'd like to write up a support script that can be used with the CLI for
your favorite password manager, add it to the `contrib/` directory.

## Adding new service providers

There are two ways to define a service provider: declarative with YAML, or procedural
by writing Python code directly.

It is recommended to try to write YAML providers since they are generally more maintainable.

If a feature is missing from the YAML handler, it is suggested to implement the needed component
so other provider configs may benefit also.

In either case, service providers are added to the `passrotate/providers/` directory. YAML files
are discovered automatically.

### YAML service provider configuration

A provider YAML consists of the following components at the root of the document:

| key | description |
|-----|-------------|
| name | The name of the service shown to the user |
| domains | A list of hostnames of the service |
| options | A mapping of option name to `OptionSpec`. Options are stored as variables of the same name. |
| prepare | A list of `FlowSpec`s that define the prepare stage |
| execute | A list of `FlowSpec`s that define the execute stage |

`OptionSpec`:

Either:

- A string: The option description shown to the user
- A dictionary:
    - `description`: The option description shown to the user
    - `options`: If given: a mapping of option name to option value.
                    Otherwise the option is a basic string option.
    - `optional`: Whether the option can be omitted.

`FlowSpec`:

A `FlowSpec` defines a single _Flow_. A Flow is a collection of individual components that define
a logical step when interacting with the website/API.

Not all steps on a given website may be nicely broken down into what a Flow defines, leading to
an unusual looking sequence, however the Flow order should match quite closely with most sites.

In the YAML file, a `FlowSpec` is a mapping of component type to component arguments. Order within
a `FlowSpec` is not important since Flows will always be in the same order, however a list of
`FlowSpec`s will always be run in sequence.

The ordering of components in a Flow is defined as:

- if_match
- prompt
- set_variable
- set_cookie
- get_url
- store_js_json
- store_url
- store_cookie
- store_element
- store_json
- match_form
- match_any_form
- action

All components in a flow are optional, however at least one comment must be given.

#### Components

**if_match**

Argument type: `MatchSpec`

If the provided `MatchSpec` matches the state of execution, the rest of the flow is executed.
Otherwise, this flow is skipped.

**prompt**

Request input from the user and store the result into a variable.

Arguments:

- `type`: Prompt type. One of TOTP, SMS, CAPTCHA, GENERIC
- `variable`: Variable name to store the value

**set_variable**

Sets a variable's value to the interpolated result of `value`.

Arguments:

- `variable`: Variable name to store the value
- `value`: A `Formatted` string of the value of the variable

**set_cookie**

Sets a cookie on the session from the given parameters.

Arguments:

- `name`: A `Formatted` string defining the cookie's name
- `value`: A `Formatted` string holding the cookie's value

Other arguments, such as `domain` and `path` are passed (after their `Formatted` values are formatted), to
[RequestsCookieJar.set](https://2.python-requests.org/en/master/api/#requests.cookies.RequestsCookieJar.set).

**get_url**

Performs an HTTP GET request on the given url, using options configured by the arguments below.

Arguments:

- `url`: A `UrlSpec` - the url to retrieve
- `headers` (optional, default: `{}`): A mapping of HTTP headers to provide to the request. Values are `Formatted` strings.
- `follow_redirects` (optional, default: `true`): Boolean Whether to follow redirects

As a shortcut, the argument may be a (`Formatted`) string directly, taken to be the `UrlSpec`, e.g:

`get_url: "https://example.com"`

**store_js_json**

Iterates over all `<script>` elements in the current document. If the given regex matches the text content
of a script, the _first_ regex group is parsed as JSON and stored in the given variable.

Arguments:

- `match`: Regular expression to match JSON data.
- `variable`: A variable name to store the parsed JSON data

**store_url**

Extract part of the current URL and store it in a variable.

Arguments:

- A mapping of URL part (path, query, etc) to either a variable name or a dictionary.

To store the whole URL part in a variable, give just the variable name. Otherwise, the dictionary
must contain:

- `match`: Regular expression to match the URL part. The first group is taken as the value
- `variable`: Variable name to store the matched value

Example:

Store the hostname in a variable `the_hostname` and the last component of the path
(`c` in `/a/b/c`) in `last_path_component`.
```
store_url:
  netloc: the_hostname
  path:
    match: "(?:/.+)*/(.+)$"
    variable: last_path_component
```

**store_cookie**

Store a cookie in the current session into a variable.

Arguments: Mapping of cookie name to variable name.

**store_element**

Match an element in the current document and store one of its properties as a variable.

Arguments:

- `element`: Element tag name to look for
- `attrs`: Mapping of attribute name to (`Formatted`) string. Only elements matching the name/value
    combination are considered for element matching.
- `store`: a dictionary with properties:
    - `variable`: Variable name to store result into
    - One of `attr` or `text`:
        - If `attr`: The value of the `attr` field is taken to be the attribute name of the element
        - Otherwise, `text` is a regular expression, where the result of the first group is stored.

**store_json**

Interpret the current response as JSON data and store the parsed data in the given variable.

Takes as argument: the variable name to store data into.

**match_form**

Matches a form in the current document and saves it's parameters ready for the `submit_form` action.

Also allows filling a form's value from a variable or user prompt.

Takes as argument:  A list of form match specifications.

A form match specification is on of two options:

A field match:

- `field`: Field name, a candidate form must have a field with this name
- `value`|`fill`|`prompt`: Defined as:
    - `value`: The value of the form field must equal this `Formatted` string
    - `fill`: Sets the form data for this field to the given `Formatted` string
    - `prompt`: Sets the form data to the prompt of the given prompt type
                (One of TOTP, SMS, CAPTCHA, GENERIC)

An attribute match:

- `attr`: Attribute name
- `value`: `Formatted` string the attribute must match.

**match_any_form**

Multiple-form version of `match_form`. The first form to match will satisfy this component.

**action**

Perform an action. This component often defines the desired outcome of the Flow.

If given a simple string argument, the string is taken to be the action type, no
arguments are passed to the action handler.

Otherwise, the `action` component takes a dictionary of arguments to be passed to
the action handler. The `type` argument is required to choose the desired action handler.

Common Arguments:

- `success`: a `MatchSpec` that matches after the action has been performed. If it matches,
    the action is deemed a success. Otherwise is a failure.
- `fail` (default: die): What to do if the action fails. Options are:
    - `die`: Aborts the execution of this service provider
    - `retry`: Retries just this Flow. This should be used only when there is an anticipated
        failure (such as user providing incorrect 2FA code).
    - `restart`: Abort execution but re-run the Flow list from the beginning of the list.

The following action handler types are defined:

- **submit_form**

Submits the form matched by `match_form`.

The form's `action` attribute is joined with the current URL to result in the request URL.

Additional arguments:

- `headers` (optional, default: `{}`): A mapping of HTTP headers to provide to the request. Values are `Formatted` strings.
- `follow_redirects` (optional, default: `true`): Boolean Whether to follow redirects

- **http_(post|put|patch|get)**

Performs an HTTP request using one of the listed verbs.

Additional arguments:

One of `data` or `data_json` may be provided, but not both.

`data` is a mapping of name to `Formatted` value, and builds the request body as URL-encoded form data.

`data_json` is structured JSON data where all leaf nodes are `Formatted` strings. The request body is set to the JSON
representation of the structure. 

The `Content-Type` header is set according to the `data`/`data_json` argument.


- `headers` (optional, default: `{}`): A mapping of HTTP headers to provide to the request. Values are `Formatted` strings.
- `follow_redirects` (optional, default: `true`): Boolean Whether to follow redirects


`Formatted`:

A Python [format string](https://docs.python.org/3/library/string.html#format-string-syntax). Stored variables can be included
within a string. Python's format strings can also do nesting, useful to get data out of JSON structures.

Example:

`"Your username is {username}"`

`UrlSpec`:

Currently this is just a `Formatted` string. This will be expanded to also allow building URLs from URL components.

`MatchSpec`:

Match one or more attributes about the current state (current URL, response body, variables).

A match only succeeds if all match parts succeed (logical AND).

Matches are given by their match property and match value, refer to this table:

| property | value description |
|----------|-------------------|
| status | Value is an integer. Match succeeds if current response status code is the value |
| text_match | Value is a regular expression. Interpret the response body as text and succeed if the regex matches the text |
| path_match | Value is a regular expression. Match succeeds if current URL path matches the regex |
| query_match | Value is a dictionary of param name to regular expressions. Match succeeds if every listed query parameter matches |
| document | Value is a list of element specifications. Response is interpreted as an HTML document match succeeds if all elements are found |
| json | Value is a nested structure representing the expected JSON values. Response is interpreted as JSON data |
| variable_exists | Value is a `Formatted` string. Match succeeds if the string after formatting is non-empty |

### Python service provider implementation

Here's the bare-minimum:

```python
from passrotate.provider import Provider, ProviderOption, register_provider
from passrotate.forms import get_form
import requests

class YourProvider(Provider):
    # The docstring is shown in pass-rotate --provider-options yourprovider
    """
    [yourprovider.com]
    username=Your username
    # Other options, if applicable
    """
    name = "Your Provider"
    domains = [
        "yourprovider.com",
    ]
    options = {
        "username": ProviderOption(str, "Your username")
    }

    def __init__(self, options):
        self.username = options["username"]

    def prepare(self, old_password):
        pass # TODO

    def execute(self, old_password, new_password):
        pass # TODO

register_provider(YourProvider)
```

You'll want to import this file in `passrotate/providers/__init__.py`.

Then you have to reverse engineer the password reset process for the provider
you're trying to add. Most providers will want to use requests.Session to keep a
cookie jar available throughout the process, and them simulate a login in
prepare(). Then, in execute(), use the same session to submit the password
change form.

The reverse engineering process will largely involve your web browser's dev
tools. Use them to monitor network requests, then look for the relevant ones.
Look at forms and see what fields are present and try to deduce what's required
to complete the process. Look for notable cookies, and for things like CSRF
tokens. Check if your provider uses two-factor authentication, and test your
code with it enabled and disabled.

You can use `passrotate.form.get_form` to prepare a dict suitable for submission
to requests.Session.post derived from the inputs on a form in the response text.
Then you can add to this the appropriate fields from your options and the
supplied passwords.
