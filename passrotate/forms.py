from typing import Dict, Callable
from bs4 import BeautifulSoup
from bs4.element import ResultSet

FormData = Dict[str, str]


def get_form_data(inputs: ResultSet) -> FormData:
    """Returns data dictionary from list of BeautifulSoup input elements.

    Parameters:
        inputs: The list of BeautifulSoup input elements.

    Returns dictionary with (name, value) pairs from inputs.
    """
    data = {}
    for i in inputs:
        name = i.get("name")
        if not name:
            continue
        if i.name == "input":
            if i.get("type") in ["checkbox", "radio"] \
               and not i.has_attr("checked"):
                continue
            value = i.get("value", "")
        elif i.name == "select":
            option = i.find("option", selected=True)
            if option is None:
                continue
            value = option.get("value", "")
        data[name] = value
    return data


def get_form(text: str, type: str = "form", **kwargs) -> FormData:
    """Helper method to get the data from a form.

    Parameters:
        text: HTML text to be processed.
        type: HTML element type to find in page.
        **kwargs: Additional parameters to pass to `soup.find()`

    Returns dictionary with (name, value) pairs from inputs from first match.
    """
    soup = BeautifulSoup(text, "html5lib")
    form = soup.find(type, attrs=kwargs)
    inputs = form.find_all("input") + form.find_all("select")
    return get_form_data(inputs)


def custom_get_form(text: str,
                    func: Callable[[BeautifulSoup], ResultSet]) -> FormData:
    """Helper method to get data from a form using a custom function.

    Parameters:
        text: HTML text to be processed.
        func: A function that takes in a BeautifulSoup object and outputs a
              list of input objects from the form desired.

    Returns dictionary with (name, value) pairs from inputs returned by func.
    """
    soup = BeautifulSoup(text, "html5lib")
    inputs = func(soup)
    return get_form_data(inputs)
