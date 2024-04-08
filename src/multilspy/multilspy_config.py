"""
Configuration parameters for Multilspy.
"""

from enum import Enum
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import pathlib
from typing import Any, Dict, Optional, Union

from multilspy.language_servers import LanguageServers
from multilspy.multilspy_types import RuntimeDependencyPaths
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.multilspy_exceptions import MultilspyException

class Language(str, Enum):
    """
    Possible languages with Multilspy.
    """

    CSHARP = "csharp"
    PYTHON = "python"
    RUST = "rust"
    JAVA = "java"

    def __str__(self) -> str:
        return self.value

def default_language_server_init_params_file(language: Language) -> Path:
    """
    Returns the default initialization parameters file path for the given language.
    """
    if language == Language.PYTHON:
        default_init_params_relative_path = "language_servers/jedi_language_server/initialize_params.json"
    elif language == Language.JAVA:
        default_init_params_relative_path = "language_servers/eclipse_jdtls/initialize_params.json"
    elif language == Language.RUST:
        default_init_params_relative_path = "language_servers/rust_analyzer/initialize_params.json"
    elif language == Language.CSHARP:
        default_init_params_relative_path = "language_servers/omnisharp/initialize_params.json"
    else:
        raise MultilspyException(f"Language {language} not supported")
    
    return os.path.join(os.path.dirname(__file__), default_init_params_relative_path)

def validate_language_server(code_language: Language, language_server: Optional[LanguageServers]) -> Optional[LanguageServers]:
    """
    Validate the language_server field based on the code_language.
    Raises:
        ValueError: If the language_server is not compatible with the code_language.
    """
    python_language_servers = [LanguageServers.JEDI]
    java_language_servers = [LanguageServers.ECLIPSEJDTLS]
    rust_language_servers = [LanguageServers.RUSTANALYZER]
    csharp_language_servers = [LanguageServers.OMNISHARP]

    if language_server is not None:
        if code_language == Language.PYTHON and language_server not in python_language_servers:
            raise ValueError(f"Invalid language server '{language_server}' for code language '{code_language}'")
        elif code_language == Language.JAVA and language_server not in java_language_servers:
            raise ValueError(f"Invalid language server '{language_server}' for code language '{code_language}'")
        elif code_language == Language.RUST and language_server not in rust_language_servers:
            raise ValueError(f"Invalid language server '{language_server}' for code language '{code_language}'") 
        elif code_language == Language.CSHARP and language_server not in csharp_language_servers:
            raise ValueError(f"Invalid language server '{language_server}' for code language '{code_language}'")
    return language_server

@dataclass
class MultilspyConfig:
    """
    Configuration parameters
    """
    code_language: Language
    """
    The programming language for the language server.
    """
    trace_lsp_communication: bool = False
    """
    Whether to trace LSP communication.
    """
    language_server: Optional[LanguageServers] = field(default=None, metadata={"validator": validate_language_server})
    """
    The language server to use.
    If not specified, the language server will be inferred based on the code language.
    """
    custom_init_params_file: Optional[Union[str, Path]] = None
    """
    Path to a custom JSON file containing initialization parameters.
    """
    init_params_overrides: Optional[InitializeParams] = None
    """
    Initialization parameter overrides.
    These overrides will be merged with the initialization parameters.
    The overrides will take precedence over the parameters.

    Example:
    ```
    config = JediServerConfig(
        init_params_overrides=InitializeParams(
            capabilities=ClientCapabilities(
                textDocument=TextDocumentClientCapabilities(
                    completion=CompletionClientCapabilities(
                        completionItem=CompletionItemClientCapabilities(
                            snippetSupport=True
                        )
                    )
                )
            )
        )
    )
    ```
    """
    repository_absolute_path: Optional[str] = None
    """
    The absolute path to the repository.
    Overrides the rootPath and rootUri in the initialization parameters and is used to set the workspaceFolders.
    """

    def get_initialization_params(self) -> InitializeParams:
        """
        Retrieve the initialization parameters for the language server.
        
        The parameters are obtained by merging the default parameters,
        custom parameters from the specified file (if provided),
        and the parameter overrides (if provided).

        Returns:
            An instance of InitializeParams containing the merged initialization parameters.
        """
        if self.custom_init_params_file:
            init_params: InitializeParams = self._read_custom_init_params()
        else:
            init_params: InitializeParams = self._read_default_init_params()
        
        if self.init_params_overrides:
            init_params: InitializeParams = InitializeParams({**init_params, **self.init_params_overrides})

        if self.repository_absolute_path:
            init_params["rootPath"] = self.repository_absolute_path
            init_params["rootUri"] = pathlib.Path(self.repository_absolute_path).as_uri()
            if "workspaceFolders" in init_params:
                init_params["workspaceFolders"] = [
                    {
                        "uri": pathlib.Path(self.repository_absolute_path).as_uri(),
                        "name": os.path.basename(self.repository_absolute_path),
                    }
                ]
                
        else:
            if init_params["rootPath"] == "$rootPath":
                raise MultilspyException("rootPath is set to `$rootPath` in initialization parameters and `repository_absolute_path` not provided in the configuration")
            
        init_params["processId"] = os.getpid()
        
        return init_params    

    def _read_default_init_params(self) -> InitializeParams:
        """
        Read the default initialization parameters from the JSON file.
        
        Returns:
            An instance of InitializeParams containing the default parameters.
        """
        default_init_params_file = default_language_server_init_params_file(self.code_language)
        try:
            with open(default_init_params_file, "r") as f:
                default_params = json.load(f)
            return InitializeParams(**default_params)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise MultilspyException(f"Error reading default initialization parameters file: {str(e)}") from e

    def _read_custom_init_params(self) -> InitializeParams:
        """
        Read the custom initialization parameters from the specified JSON file (if provided).
        
        Returns:
            An instance of InitializeParams containing the custom parameters,
            or an empty InitializeParams instance if no custom file is specified.
        """
        if self.custom_init_params_file:
            try:
                with open(self.custom_init_params_file, "r") as f:
                    custom_params = json.load(f)
                return InitializeParams(**custom_params)
            except json.JSONDecodeError as e:
                raise MultilspyException(f"Error reading custom initialization parameters file: {str(e)}") from e
        else:
            return InitializeParams()

    @classmethod
    def from_dict(cls, env: Dict[str, Any]):
        """
        Create a MultilspyConfig instance from a dictionary
        """
        import inspect
        return cls(**{
            k: v for k, v in env.items() 
            if k in inspect.signature(cls).parameters
        })
    
@dataclass
class JediServerConfig(MultilspyConfig):
    """
    Configuration class for the Jedi language server.
    """
    code_language: Language = field(default=Language.PYTHON, init=False)
    language_server: LanguageServers = field(default=LanguageServers.JEDI, init=False)
    environment_path: Optional[str] = None


@dataclass
class EclipseJDTLSConfig(MultilspyConfig):
    """
    Configuration class for the Eclipse JDTLS language server.
    """
    code_language: Language = field(default=Language.JAVA, init=False)
    language_server: LanguageServers = field(default=LanguageServers.ECLIPSEJDTLS, init=False)

@dataclass
class EclipseJDTLSConfig(MultilspyConfig):
    """
    Configuration class for the Eclipse JDTLS language server.
    """
    code_language: Language = field(default=Language.JAVA, init=False)
    language_server: LanguageServers = field(default=LanguageServers.ECLIPSEJDTLS, init=False)
    runtime_dependency_paths: Optional[RuntimeDependencyPaths] = None

    def get_initialization_params(self) -> InitializeParams:
        init_params = super().get_initialization_params()
        
        if not os.path.isabs(self.repository_absolute_path):
            self.repository_absolute_path = os.path.abspath(self.repository_absolute_path)
        
        if "initializationOptions" not in init_params:
            init_params["initializationOptions"] = {}
        
        init_params["initializationOptions"]["workspaceFolders"] = [pathlib.Path(self.repository_absolute_path).as_uri()]
        init_params["workspaceFolders"] = [
            {
                "uri": pathlib.Path(self.repository_absolute_path).as_uri(),
                "name": os.path.basename(self.repository_absolute_path),
            }
        ]
        
        if self.runtime_dependency_paths:
            init_params["initializationOptions"]["bundles"] = [self.runtime_dependency_paths.intellicode_jar_path]
            
            init_params["initializationOptions"].setdefault("settings", {}).setdefault("java", {}).setdefault("configuration", {})["runtimes"] = [
                {"name": "JavaSE-17", "path": self.runtime_dependency_paths.jre_home_path, "default": True}
            ]
            
            for runtime in init_params["initializationOptions"]["settings"]["java"]["configuration"]["runtimes"]:
                assert "name" in runtime
                assert "path" in runtime
                assert os.path.exists(runtime["path"]), f"Runtime required for eclipse_jdtls at path {runtime['path']} does not exist"
            
            init_params["initializationOptions"].setdefault("settings", {}).setdefault("java", {}).setdefault("import", {}).setdefault("gradle", {})["home"] = self.runtime_dependency_paths.gradle_path
            init_params["initializationOptions"]["settings"]["java"]["import"]["gradle"].setdefault("java", {})["home"] = self.runtime_dependency_paths.jre_path
        
        return init_params
    
@dataclass
class RustAnalyzerConfig(MultilspyConfig):
    """
    Configuration class for the Rust Analyzer language server.
    """
    code_language: Language = field(default=Language.RUST, init=False)
    language_server: LanguageServers = field(default=LanguageServers.RUSTANALYZER, init=False)

@dataclass
class OmniSharpConfig(MultilspyConfig):
    """
    Configuration class for the OmniSharp language server.
    """
    code_language: Language = field(default=Language.CSHARP, init=False)
    language_server: LanguageServers = field(default=LanguageServers.OMNISHARP, init=False)