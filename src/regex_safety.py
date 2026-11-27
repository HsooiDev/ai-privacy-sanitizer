"""Static and empirical ReDoS safety validation for user-defined custom regex rules."""

from dataclasses import dataclass
import re
import time
from typing import FrozenSet, Optional, Pattern, Tuple

try:
    import re._parser as _re_parser  # Python 3.11+
    import re._constants as _re_constants
except ImportError:  # pragma: no cover - Python 3.10 fallback
    import sre_parse as _re_parser  # type: ignore
    import sre_constants as _re_constants  # type: ignore


MAX_CUSTOM_REGEX_LENGTH = 512
PROBE_TIMEOUT_SECONDS = 0.05
RUNTIME_RULE_TIMEOUT_SECONDS = 0.25

ALLOWED_PLACEHOLDER_TEMPLATES: Tuple[str, ...] = (
    "[{category}_{index}]",
    "<{category}_{index}>",
    "{{{category}_{index}}}",
)

_REPEAT_OPS = frozenset(
    op
    for op in (
        getattr(_re_constants, "MAX_REPEAT", None),
        getattr(_re_constants, "MIN_REPEAT", None),
        getattr(_re_constants, "POSSESSIVE_REPEAT", None),
    )
    if op is not None
)
_SUBPATTERN_OP = _re_constants.SUBPATTERN
_BRANCH_OP = _re_constants.BRANCH
_GROUPREF_OP = _re_constants.GROUPREF
_ANY_OP = _re_constants.ANY
_LITERAL_OP = _re_constants.LITERAL
_NOT_LITERAL_OP = _re_constants.NOT_LITERAL
_IN_OP = _re_constants.IN
_RANGE_OP = _re_constants.RANGE
_CATEGORY_OP = _re_constants.CATEGORY
_AT_OP = _re_constants.AT
_ASSERT_OP = getattr(_re_constants, "ASSERT", None)
_ASSERT_NOT_OP = getattr(_re_constants, "ASSERT_NOT", None)
_MAXREPEAT = _re_constants.MAXREPEAT

_ADVERSARIAL_PROBES: Tuple[str, ...] = (
    "a" * 28 + "!",
    "0" * 28 + "!",
    "a_1-" * 8 + "!",
    "X" * 28 + "?",
)


class RegexSafetyError(ValueError):
    """Raised when a user-defined regex is syntactically invalid or unsafe for ReDoS."""


class RegexTimeoutError(RuntimeError):
    """Raised when a regex exceeds the runtime evaluation deadline."""


@dataclass(frozen=True)
class CompiledCustomRule:
    """Validated and compiled user-defined custom regex rule."""

    name: str
    category: str
    pattern_text: str
    pattern: Pattern[str]
    placeholder_template: str
    target_group: str
    enabled: bool = True


def _can_match_empty(subpattern) -> bool:
    for op, av in subpattern:
        if op == _AT_OP or op in (_ASSERT_OP, _ASSERT_NOT_OP):
            continue
        if op in _REPEAT_OPS:
            min_rep, _max_rep, inner = av
            if min_rep == 0 or _can_match_empty(inner):
                continue
            return False
        if op == _SUBPATTERN_OP:
            if not _can_match_empty(av[-1]):
                return False
            continue
        if op == _BRANCH_OP:
            if any(_can_match_empty(branch) for branch in av[1]):
                continue
            return False
        return False
    return True


def _branch_broad_overlap(branches) -> bool:
    """Detect obvious overlapping or empty branches inside a repeated alternation."""
    if len(branches) <= 1:
        return False
    seen_prefixes: list[Optional[FrozenSet[int]]] = []
    for branch in branches:
        if _can_match_empty(branch):
            return True
        first_chars: Optional[FrozenSet[int]] = _first_char_hint(branch)
        for prev in seen_prefixes:
            if prev is None or first_chars is None:
                return True
            if prev & first_chars:
                return True
        seen_prefixes.append(first_chars)
    return False


def _first_char_hint(subpattern) -> Optional[FrozenSet[int]]:
    """Return a conservative set of possible first char ordinals, or None if broad/unknown."""
    for op, av in subpattern:
        if op == _AT_OP or op in (_ASSERT_OP, _ASSERT_NOT_OP):
            continue
        if op == _LITERAL_OP:
            return frozenset((av,))
        if op == _IN_OP:
            chars = set()
            for item_op, item_av in av:
                if item_op == _LITERAL_OP:
                    chars.add(item_av)
                elif item_op == _RANGE_OP and (item_av[1] - item_av[0]) <= 64:
                    chars.update(range(item_av[0], item_av[1] + 1))
                else:
                    return None
            return frozenset(chars)
        if op == _SUBPATTERN_OP:
            return _first_char_hint(av[-1])
        return None
    return None


def _inspect_ast(subpattern, *, in_unbounded_repeat: bool = False) -> None:
    for op, av in subpattern:
        if op in _REPEAT_OPS:
            min_rep, max_rep, inner = av
            is_multi = max_rep == _MAXREPEAT or max_rep > 1
            if in_unbounded_repeat and is_multi:
                raise RegexSafetyError("Nested quantifiers are blocked to prevent catastrophic backtracking (ReDoS)")
            next_repeat = in_unbounded_repeat or (max_rep == _MAXREPEAT or max_rep > 5)
            _inspect_ast(inner, in_unbounded_repeat=next_repeat)
        elif op == _SUBPATTERN_OP:
            _inspect_ast(av[-1], in_unbounded_repeat=in_unbounded_repeat)
        elif op == _BRANCH_OP:
            branches = av[1]
            if in_unbounded_repeat and _branch_broad_overlap(branches):
                raise RegexSafetyError("Overlapping or empty alternation inside quantifier risks catastrophic backtracking")
            for branch in branches:
                _inspect_ast(branch, in_unbounded_repeat=in_unbounded_repeat)
        elif op == _GROUPREF_OP:
            if in_unbounded_repeat:
                raise RegexSafetyError("Backreferences inside quantifiers are blocked for ReDoS safety")
        elif op in (_ASSERT_OP, _ASSERT_NOT_OP):
            _inspect_ast(av[1], in_unbounded_repeat=in_unbounded_repeat)


def validate_custom_regex(pattern: str, sample_text: str = "") -> Tuple[Pattern[str], str]:
    """Compile and statically/empirically validate a user-defined regex against ReDoS."""
    if not isinstance(pattern, str) or not pattern.strip():
        raise RegexSafetyError("Regex pattern cannot be empty")
    if len(pattern) > MAX_CUSTOM_REGEX_LENGTH:
        raise RegexSafetyError(f"Regex pattern exceeds {MAX_CUSTOM_REGEX_LENGTH} characters")

    try:
        parsed = _re_parser.parse(pattern)
        compiled = re.compile(pattern)
    except re.error as exc:
        raise RegexSafetyError(f"Invalid regex syntax: {exc}") from exc

    if compiled.fullmatch("") is not None or _can_match_empty(parsed):
        raise RegexSafetyError("Regex must not match empty or zero-width strings")

    _inspect_ast(parsed, in_unbounded_repeat=False)

    probes = list(_ADVERSARIAL_PROBES)
    if sample_text:
        probes.append(sample_text[:2000])
    for probe in probes:
        t0 = time.perf_counter()
        compiled.search(probe)
        elapsed = time.perf_counter() - t0
        if elapsed > PROBE_TIMEOUT_SECONDS:
            raise RegexSafetyError("Regex exceeded safety timing threshold (possible backtracking)")

    target_group = "secret" if "secret" in compiled.groupindex else ""
    if target_group and compiled.groupindex[target_group] <= 0:
        target_group = ""
    return compiled, target_group


def sanitize_category_name(category: str, default: str = "CUSTOM_REGEX") -> str:
    """Normalize a custom category name into an uppercase identifier."""
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", str(category or "").strip()).strip("_").upper()
    return cleaned or default


def validate_placeholder_template(template: str, category: str) -> str:
    """Validate placeholder template so allocated tokens remain reversible and safe."""
    tpl = str(template or "[{category}_{index}]").strip()
    if tpl not in ALLOWED_PLACEHOLDER_TEMPLATES:
        raise RegexSafetyError(
            "Placeholder template must be one of [{category}_{index}], <{category}_{index}>, or {{{category}_{index}}}"
        )
    cat = sanitize_category_name(category)
    first = tpl.format(category=cat, index=1)
    second = tpl.format(category=cat, index=2)
    if first == second or not first:
        raise RegexSafetyError("Invalid placeholder template")
    return tpl
