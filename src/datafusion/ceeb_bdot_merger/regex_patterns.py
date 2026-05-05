# -----------------------------
# Regex pattern classes
# -----------------------------
# Centralized patterns grouped by category for easier maintenance.


class StreetPatterns:
    """Regex patterns for street name processing."""

    ABBREVIATIONS = r"^ul\.|^pl\.|^os\.|^ulica"
    LEADING_WHITESPACE = r"^\s"
    ENDS_WITH_NUMBER = r"^\w.*\d+$"
    TRAILING_NUMBER_BLOCK = r"\s+\d+.*$"
    POLISH_NUMBER_SUFFIXES = r"-go|-tej|-tych|-tego|-tę|-tą|-ci|-cie|-im|-ich|-oma|-ą|-e|-i|-y|-a"
    BRACKET_CONTENT = r"\s*\([^)]*\)"


class HouseNumberPatterns:
    """Regex patterns for house number processing."""

    NO_NUMBER = r"\d"
    TOO_MANY_LETTERS = r"[a-zA-Z]{3,}"
    OFICINA_BLOCK = r"oficyna.*"
    PAREN_CONTENT = r"\(.*"
    ROD_DZIALKA = r"dzialka|dz|działka|rod|altanka|altana|garaż|R\.O\.D|-$"
    REDUNDANT_INFO = r"lokal.*|\s*-*\s*front.*|lok.*|bud.*|paw.*|pawilon.*"
    TRAILING_DASH = r"-$"
    NUMBER_DASH_DESCRIPTION = r"^(\d+)\s*-\s*(?!\d+$)(?!\d+[a-zA-Z]$)(?![a-zA-Z]$)[^-]+$"
    PUNCT_TO_REMOVE = r" |_|--|'|^-$|^,|\s"


class SlashPatterns:
    """Regex patterns for slash processing in house numbers."""

    IN_NUMBER = r"/"
    SUFFIX_CAPTURE = r"/(.+)$"
    AND_AFTER = r"/.+$"


class DashPatterns:
    """Regex patterns for dash processing in house numbers."""

    SINGLE_DASH_RANGE = r"^[^-]*-[^-]*$"
    NUMBER_BEFORE_DASH = r"(\d+)-"
    NUMBER_AFTER_DASH = r"-(\d+)"
    LETTERS_BEFORE_DASH = r"([a-zA-Z]+)-"
    LETTERS_AFTER_DASH = r"-\d*([a-zA-Z]+)"


class ExtractionPatterns:
    """Regex patterns for extracting address components."""

    BASE_NUMBER = r"\d+"
    COMMA_NUMBER_LETTERS = r"\d+[a-zA-Z]+\s*,[a-zA-Z]"
    LEADING_NUMBER = r"^(\d+)"
    ADDR_NUMBER_EXTRACT = r"(\s+\d+.* $|\s$)"
    ADDR_STREET_EXTRACT = r"(.*\w)(?=\s+\d+.*$)"
    I_ORAZ = r" i | oraz "
