"""
This module contains the exceptions raised by the Multilspy framework.
"""

class MultilspyException(Exception):
    """
    Exceptions raised by the Multilspy framework.
    """

    def __init__(self, message: str):
        """
        Initializes the exception with the given message.
        """
        super().__init__(message)

class LSNotFoundException(MultilspyException):
    """
    Exception raised when a language server is not found.
    """

    def __init__(self, language_server: str):
        """
        Initializes the exception with the given language server.
        """
        super().__init__("No language server implementation could be found for the given configuration")

class LSNotSupportedException(MultilspyException):
    """
    Exception raised when a language server is not supported.
    """

    def __init__(self, language_server: str):
        """
        Initializes the exception with the given language server.
        """
        super().__init__(f"Language server {language_server} not supported")