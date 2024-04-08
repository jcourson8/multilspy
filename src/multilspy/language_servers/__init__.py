from enum import Enum

class LanguageServers(str, Enum):
    """
    Possible language servers with Multilspy.
    """

    JEDI = "JediServer"
    ECLIPSEJDTLS = "EclipseJDTLS"
    RUSTANALYZER = "RustAnalyzer"
    OMNISHARP = "OmniSharp"

    def __str__(self) -> str:
        return self.value