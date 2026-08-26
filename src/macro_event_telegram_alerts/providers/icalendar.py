"""Small RFC 5545 content-line parser for calendar event ingestion."""

from dataclasses import dataclass


class ICalendarParseError(ValueError):
    """The calendar is structurally invalid or unsupported."""


@dataclass(frozen=True, slots=True)
class CalendarProperty:
    """One unfolded iCalendar content line."""

    name: str
    value: str
    parameters: tuple[tuple[str, str], ...] = ()

    def parameter(self, name: str) -> str | None:
        """Return a case-insensitive parameter value, if present."""
        normalized_name = name.upper()
        return next(
            (value for key, value in self.parameters if key == normalized_name),
            None,
        )


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """Properties captured from one VEVENT component."""

    properties: tuple[CalendarProperty, ...]

    def require_one(self, name: str) -> CalendarProperty:
        """Return exactly one named property or fail visibly."""
        matches = self._matching(name)
        if len(matches) != 1:
            raise ICalendarParseError(
                f"VEVENT must contain exactly one {name.upper()} property"
            )
        return matches[0]

    def optional_one(self, name: str) -> CalendarProperty | None:
        """Return zero or one named property, rejecting duplicates."""
        matches = self._matching(name)
        if len(matches) > 1:
            raise ICalendarParseError(
                f"VEVENT must not contain multiple {name.upper()} properties"
            )
        return matches[0] if matches else None

    def _matching(self, name: str) -> tuple[CalendarProperty, ...]:
        normalized_name = name.upper()
        return tuple(prop for prop in self.properties if prop.name == normalized_name)


def parse_icalendar(text: str) -> tuple[CalendarEvent, ...]:
    """Parse VEVENT properties from an RFC 5545 calendar document."""
    lines = _unfold_content_lines(text)
    if not lines:
        raise ICalendarParseError("calendar is empty")

    properties = tuple(_parse_content_line(line) for line in lines)
    if properties[0] != CalendarProperty(name="BEGIN", value="VCALENDAR"):
        raise ICalendarParseError("calendar must begin with BEGIN:VCALENDAR")
    if properties[-1] != CalendarProperty(name="END", value="VCALENDAR"):
        raise ICalendarParseError("calendar must end with END:VCALENDAR")

    components: list[str] = []
    current_event: list[CalendarProperty] | None = None
    events: list[CalendarEvent] = []

    for prop in properties:
        if prop.name == "BEGIN":
            component = prop.value.upper()
            if component == "VEVENT" and current_event is not None:
                raise ICalendarParseError("VEVENT components cannot be nested")
            components.append(component)
            if component == "VEVENT":
                current_event = []
            continue

        if prop.name == "END":
            component = prop.value.upper()
            if not components or components[-1] != component:
                raise ICalendarParseError(f"unexpected END:{component}")
            if component == "VEVENT":
                if current_event is None:
                    raise ICalendarParseError("VEVENT end has no matching begin")
                events.append(CalendarEvent(properties=tuple(current_event)))
                current_event = None
            components.pop()
            continue

        if current_event is not None and components[-1] == "VEVENT":
            current_event.append(prop)

    if components:
        raise ICalendarParseError(f"unclosed {components[-1]} component")
    return tuple(events)


def unescape_text(value: str) -> str:
    """Unescape an RFC 5545 TEXT property value."""
    output: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character != "\\":
            output.append(character)
            index += 1
            continue
        if index + 1 >= len(value):
            raise ICalendarParseError("TEXT value ends with an escape character")
        escaped = value[index + 1]
        if escaped in {"n", "N"}:
            output.append("\n")
        elif escaped in {"\\", ",", ";"}:
            output.append(escaped)
        else:
            raise ICalendarParseError(f"unsupported TEXT escape: \\{escaped}")
        index += 2
    return "".join(output)


def _unfold_content_lines(text: str) -> tuple[str, ...]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    unfolded: list[str] = []
    for line in normalized.split("\n"):
        if line.startswith((" ", "\t")):
            if not unfolded:
                raise ICalendarParseError("calendar begins with a folded line")
            unfolded[-1] += line[1:]
        elif line:
            unfolded.append(line)
    return tuple(unfolded)


def _parse_content_line(line: str) -> CalendarProperty:
    head, separator, value = line.partition(":")
    if not separator or not head:
        raise ICalendarParseError("content line must contain a name and colon")

    segments = head.split(";")
    name = segments[0].upper()
    if not name:
        raise ICalendarParseError("content line property name is empty")

    parameters: list[tuple[str, str]] = []
    parameter_names: set[str] = set()
    for segment in segments[1:]:
        key, equals, parameter_value = segment.partition("=")
        key = key.upper()
        if not equals or not key or not parameter_value:
            raise ICalendarParseError(f"invalid parameter on {name}")
        if key in parameter_names:
            raise ICalendarParseError(f"duplicate {key} parameter on {name}")
        parameter_names.add(key)
        parameters.append((key, parameter_value.strip('"')))

    return CalendarProperty(
        name=name,
        value=value,
        parameters=tuple(parameters),
    )
