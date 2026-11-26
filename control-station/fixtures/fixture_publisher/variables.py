"""cs/variables/<key>: check the value against the spec file, keep it, and publish the spec again (IF-07)."""
from shared import topics as T
from shared.interfaces import ValidationError, validate
from topic_table import STAND_IN_PROGRAMS, Publication, publication, writer_of

ENVELOPE = {"timestamp_s": 0.0, "seq": 0, "version": 1}


class VariableSpecs:
    def __init__(self, specs: dict[str, list[dict]]) -> None:
        """Raises ValueError, naming the key, when a key or a variable in the file is wrong."""
        _check_specs(specs)
        self._specs = {key: tuple(variables) for key, variables in specs.items()}

    def start_publications(self) -> list[Publication]:
        return [self._publication(key) for key in self._specs]

    def owner_of(self, key: str) -> str | None:
        return writer_of(T.variables_spec(key)) if key in self._specs else None

    def answer(self, key: str, msg: dict) -> list[Publication]:
        """The owner's spec with the values in use: numbers clamped to min..max, other wrong values left as they were."""
        if key not in self._specs:
            return []
        self._specs[key] = tuple(_with_checked_value(spec, msg[spec["name"]]) if spec["name"] in msg else spec
                                 for spec in self._specs[key])
        return [self._publication(key)]

    def _publication(self, key: str) -> Publication:
        return publication(T.variables_spec(key), {"variables": list(self._specs[key])})


def _check_specs(specs: dict[str, list[dict]]) -> None:
    for key, variables in specs.items():
        owner = T.KEY_OWNER.get(key)
        if owner is None:
            raise ValueError(f"unknown key {key!r}; allowed: {sorted(T.KEY_OWNER)}")
        if owner not in STAND_IN_PROGRAMS:
            raise ValueError(f"{key} belongs to {owner}, which this publisher does not stand in for")
        try:
            validate(T.variables_spec(key), {**ENVELOPE, "writer": owner, "variables": variables})
        except ValidationError as error:
            raise ValueError(f"{key}: {error.message}") from None


def _with_checked_value(spec: dict, value) -> dict:
    if spec["choices"] is not None:
        checked = value if value in spec["choices"] else None
    elif isinstance(spec["value"], bool):
        checked = value if isinstance(value, bool) else None
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        checked = min(max(value, spec["min"]), spec["max"])
    else:
        checked = None
    return spec if checked is None else {**spec, "value": checked}
