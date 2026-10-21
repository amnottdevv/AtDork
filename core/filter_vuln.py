"""
AtDork vulnerability filtering helpers.

Default wordlists are loaded from packaged resources so the filters work from an
installed wheel, not only from a repository checkout.
"""

import logging
import os
import re
from collections import deque
from importlib import resources
from typing import Deque, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

DEFAULT_WORDLIST_DIR = "wordlists"
WORDLIST_PACKAGE = "wordlists"
PACKAGE_PREFIX = "pkg://"

# Cache: key = resolved resource id, value = compiled regex patterns
_wordlist_cache: Dict[str, List[re.Pattern]] = {}
# Cache: key = resolved resource id, value = prefilter index (see _FilterIndex)
_index_cache: Dict[str, "_FilterIndex"] = {}

# A pattern that contains any of these cannot be reduced to a required literal.
# `-` is harmless and stays out of the class.
_REGEX_META = re.compile(r"[\\\[\]()|*+?{}^$]")
_DOT = re.compile(r"\.")


class _AhoCorasick:
    """Minimal Aho-Corasick automaton (pure Python, read-only after build()).

    It answers one question fast: which required literals occur in this text?
    The original regexes still make the final match decision, so the automaton
    only acts as a conservative candidate filter.
    """

    __slots__ = ("_goto", "_fail", "_out")

    def __init__(self) -> None:
        self._goto: List[Dict[str, int]] = [{}]
        self._fail: List[int] = [0]
        self._out: List[List[int]] = [[]]

    def add(self, word: str, payload: int) -> None:
        node = 0
        for ch in word:
            nxt = self._goto[node].get(ch)
            if nxt is None:
                nxt = len(self._goto)
                self._goto[node][ch] = nxt
                self._goto.append({})
                self._fail.append(0)
                self._out.append([])
            node = nxt
        self._out[node].append(payload)

    def build(self) -> None:
        queue: Deque[int] = deque(self._goto[0].values())
        while queue:
            node = queue.popleft()
            for ch, child in self._goto[node].items():
                queue.append(child)
                fail = self._fail[node]
                while fail and ch not in self._goto[fail]:
                    fail = self._fail[fail]
                self._fail[child] = self._goto[fail].get(ch, 0)
                self._out[child].extend(self._out[self._fail[child]])

    def candidates(self, text: str) -> Set[int]:
        node = 0
        found: Set[int] = set()
        goto, fail, out = self._goto, self._fail, self._out
        for ch in text:
            while node and ch not in goto[node]:
                node = fail[node]
            node = goto[node].get(ch, 0)
            if out[node]:
                found.update(out[node])
        return found


class _FilterIndex:
    """Required-literal prefilter for one compiled wordlist."""

    __slots__ = ("automaton", "always")

    def __init__(self, automaton: _AhoCorasick, always: Tuple[int, ...]) -> None:
        self.automaton = automaton
        self.always = always


def _required_literal(pattern: str) -> Optional[str]:
    """Return a literal every match of ``pattern`` must contain, if provable.

    Wordlist entries are regexes, but in practice almost all of them are plain
    paths where ``.`` is the only metacharacter. Splitting on ``.`` yields
    literal segments; at least one full segment must appear in any match, so
    the longest segment is a safe necessary condition. Anything more complex
    (classes, alternation, anchors, escapes, non-ASCII case folding) returns
    ``None`` and is always evaluated with the real regex.
    """
    if _REGEX_META.search(pattern) or not pattern.isascii():
        return None
    segments = [segment for segment in _DOT.split(pattern) if segment]
    if not segments:
        return None
    return max(segments, key=len)


def _build_filter_index(patterns: List[re.Pattern]) -> _FilterIndex:
    automaton = _AhoCorasick()
    always: List[int] = []
    for idx, pattern in enumerate(patterns):
        literal = _required_literal(pattern.pattern)
        if literal is None:
            always.append(idx)
        else:
            # casefold() is at least as permissive as re.IGNORECASE for the
            # ASCII literals accepted above, so it cannot hide a real match.
            automaton.add(literal.casefold(), idx)
    automaton.build()
    return _FilterIndex(automaton, tuple(always))


def _is_default_wordlist_dir(wordlist_dir: str) -> bool:
    return os.path.normpath(wordlist_dir) == os.path.normpath(DEFAULT_WORDLIST_DIR)


def _package_resource_id(package: str, resource_name: str) -> str:
    return f"{PACKAGE_PREFIX}{package}/{resource_name}"


def _parse_package_resource(resource_id: str) -> Tuple[str, str]:
    relative = resource_id[len(PACKAGE_PREFIX):]
    package, _, resource_name = relative.rpartition("/")
    return package, resource_name


def _resource_exists(filename: str, wordlist_dir: str) -> bool:
    if _is_default_wordlist_dir(wordlist_dir):
        try:
            return resources.files(WORDLIST_PACKAGE).joinpath(filename).is_file()
        except ModuleNotFoundError:
            return False
    return os.path.isfile(os.path.join(wordlist_dir, filename))


def _describe_wordlist_source(wordlist_dir: str) -> str:
    if _is_default_wordlist_dir(wordlist_dir):
        return f"package resource '{WORDLIST_PACKAGE}'"
    return f"directory '{os.path.abspath(wordlist_dir)}'"


def resolve_filter_arg(filter_arg: str, wordlist_dir: str = DEFAULT_WORDLIST_DIR) -> Tuple[str, str, str]:
    """
    Resolve a filter name into its wordlist resource.

    Returns:
        Tuple (base_name, filter_type, resource_id_or_path)
    """
    if filter_arg.endswith("-link") or filter_arg.endswith("-url"):
        filter_type = "link"
        base_name = re.sub(r"-(link|url)$", "", filter_arg)
    else:
        filter_type = "path"
        base_name = filter_arg

    filename = f"{filter_arg}.txt"

    if _is_default_wordlist_dir(wordlist_dir):
        if _resource_exists(filename, wordlist_dir):
            return base_name, filter_type, _package_resource_id(WORDLIST_PACKAGE, filename)
    else:
        filepath = os.path.abspath(os.path.join(wordlist_dir, filename))
        if os.path.isfile(filepath):
            return base_name, filter_type, filepath

    error_msg = [
        f"Wordlist file '{filename}' not found.",
        f"   Checked source: {_describe_wordlist_source(wordlist_dir)}",
    ]

    if filter_arg.endswith("-link"):
        base = filter_arg[:-5]
        base_filename = f"{base}.txt"
        if _resource_exists(base_filename, wordlist_dir):
            error_msg.append(
                f"   Tip: Found '{base_filename}'. Did you mean '--filter-vuln {base}'?"
            )
    else:
        link_filename = f"{filter_arg}-link.txt"
        if _resource_exists(link_filename, wordlist_dir):
            error_msg.append(
                f"   Tip: Found '{link_filename}'. Did you mean '--filter-vuln {filter_arg}-link'?"
            )

    raise FileNotFoundError("\n".join(error_msg))


def load_wordlist(path: str) -> List[re.Pattern]:
    """
    Load a wordlist and compile each non-empty line into a regex pattern.
    """
    if path.startswith(PACKAGE_PREFIX):
        package, resource_name = _parse_package_resource(path)
        resource = resources.files(package).joinpath(resource_name)
        if not resource.is_file():
            raise FileNotFoundError(f"Wordlist not found: {path}")
        stream = resource.open("r", encoding="utf-8")
    else:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Wordlist not found: {path}")
        stream = open(path, "r", encoding="utf-8")

    patterns = []
    with stream as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                patterns.append(re.compile(line, re.IGNORECASE))
            except re.error as exc:
                logger.warning("Invalid regex pattern in %s: %s (%s)", path, line, exc)

    logger.info("Loaded %d patterns from %s", len(patterns), path)
    return patterns


def _cache_key(location: str) -> str:
    return location if location.startswith(PACKAGE_PREFIX) else os.path.abspath(location)


def _get_patterns(location: str) -> List[re.Pattern]:
    key = _cache_key(location)
    patterns = _wordlist_cache.get(key)
    if patterns is None:
        patterns = load_wordlist(location)
        _wordlist_cache[key] = patterns
    return patterns


def _get_index(location: str, patterns: List[re.Pattern]) -> _FilterIndex:
    key = _cache_key(location)
    index = _index_cache.get(key)
    if index is None:
        index = _build_filter_index(patterns)
        _index_cache[key] = index
    return index


def get_wordlist(filter_arg: str, wordlist_dir: str = DEFAULT_WORDLIST_DIR) -> List[re.Pattern]:
    """
    Return compiled regex patterns for a filter, with caching.
    """
    _, _, location = resolve_filter_arg(filter_arg, wordlist_dir)
    return _get_patterns(location)


def _resolve_with_index(
    filter_arg: str, wordlist_dir: str = DEFAULT_WORDLIST_DIR
) -> Tuple[List[re.Pattern], str, str, _FilterIndex]:
    base_name, filter_type, location = resolve_filter_arg(filter_arg, wordlist_dir)
    patterns = _get_patterns(location)
    return patterns, filter_type, base_name, _get_index(location, patterns)


def get_filter_info(filter_arg: str, wordlist_dir: str = DEFAULT_WORDLIST_DIR) -> Tuple[List[re.Pattern], str, str]:
    """
    Return (patterns, filter_type, base_name) for a vulnerability filter.
    """
    patterns, filter_type, base_name, _ = _resolve_with_index(filter_arg, wordlist_dir)
    return patterns, filter_type, base_name


def filter_vulnerable(
    results: List[Dict],
    filter_arg: str = "wordpress",
    wordlist_dir: str = DEFAULT_WORDLIST_DIR,
    **kwargs,
) -> Tuple[List[Dict], List[Dict], str]:
    """
    Split search results into vulnerable and safe buckets.

    A required-literal (Aho-Corasick) prefilter skips the vast majority of
    regex evaluations while the real compiled patterns still decide the final
    match, so results are identical to a brute-force scan.
    """
    if "platform" in kwargs:
        filter_arg = kwargs["platform"]

    if not isinstance(results, list):
        logger.warning("filter_vulnerable: results is not a list, returning empty.")
        return [], [], "unknown"

    if not results:
        return [], [], "unknown"

    patterns, filter_type, _, index = _resolve_with_index(filter_arg, wordlist_dir)

    vulnerable = []
    safe = []

    for res in results:
        if filter_type == "link":
            # Link mode: cocokkan hanya pada href/URL (sesuai dokumentasi).
            text = f"{res.get('href', '')}"
        else:
            # Path mode: gabungkan title, href, dan body.
            text = f"{res.get('title', '')} {res.get('href', '')} {res.get('body', '')}"

        matched = False
        for idx in index.automaton.candidates(text.casefold()):
            if patterns[idx].search(text):
                matched = True
                break
        if not matched:
            for idx in index.always:
                if patterns[idx].search(text):
                    matched = True
                    break

        if matched:
            vulnerable.append(res)
        else:
            safe.append(res)

    logger.info(
        "Filter %s (type %s): %d vulnerable, %d safe out of %d total results",
        filter_arg,
        filter_type,
        len(vulnerable),
        len(safe),
        len(results),
    )
    return vulnerable, safe, filter_type
