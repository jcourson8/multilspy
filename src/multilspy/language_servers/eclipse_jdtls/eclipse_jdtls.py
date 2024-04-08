"""
Provides Java specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Java.
"""

import asyncio
import dataclasses
import json
import logging
import os
import pathlib
import shutil
import stat
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.multilspy_config import EclipseJDTLSConfig, Language, MultilspyConfig
from multilspy.multilspy_settings import MultilspySettings
from multilspy.multilspy_types import RuntimeDependencyPaths
from multilspy.multilspy_utils import FileUtils
from multilspy.multilspy_utils import PlatformUtils
from pathlib import PurePath

class EclipseJDTLS(LanguageServer):
    """
    The EclipseJDTLS class provides a Java specific implementation of the LanguageServer class
    """

    def __init__(self, config: EclipseJDTLSConfig, logger: MultilspyLogger):
        """
        Creates a new EclipseJDTLS instance initializing the language server settings appropriately.
        This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """

        initialize_params = config.get_initialization_params()

        runtime_dependency_paths = self.setupRuntimeDependencies(logger, config)
        self.runtime_dependency_paths = runtime_dependency_paths

        # ws_dir is the workspace directory for the EclipseJDTLS server
        ws_dir = str(
            PurePath(
                MultilspySettings.get_language_server_directory(),
                "EclipseJDTLS",
                "workspaces",
                uuid.uuid4().hex,
            )
        )

        # shared_cache_location is the global cache used by Eclipse JDTLS across all workspaces
        shared_cache_location = str(
            PurePath(MultilspySettings.get_global_cache_directory(), "lsp", "EclipseJDTLS", "sharedIndex")
        )

        jre_path = self.runtime_dependency_paths.jre_path
        lombok_jar_path = self.runtime_dependency_paths.lombok_jar_path

        jdtls_launcher_jar = self.runtime_dependency_paths.jdtls_launcher_jar_path

        os.makedirs(ws_dir, exist_ok=True)

        data_dir = str(PurePath(ws_dir, "data_dir"))
        jdtls_config_path = str(PurePath(ws_dir, "config_path"))

        jdtls_readonly_config_path = self.runtime_dependency_paths.jdtls_readonly_config_path

        if not os.path.exists(jdtls_config_path):
            shutil.copytree(jdtls_readonly_config_path, jdtls_config_path)

        for static_path in [
            jre_path,
            lombok_jar_path,
            jdtls_launcher_jar,
            jdtls_config_path,
            jdtls_readonly_config_path,
        ]:
            assert os.path.exists(static_path), static_path

        proc_env = {"syntaxserver": "false"}
        proc_cwd = initialize_params["rootPath"]
        cmd = " ".join(
            [
                jre_path,
                "--add-modules=ALL-SYSTEM",
                "--add-opens",
                "java.base/java.util=ALL-UNNAMED",
                "--add-opens",
                "java.base/java.lang=ALL-UNNAMED",
                "--add-opens",
                "java.base/sun.nio.fs=ALL-UNNAMED",
                "-Declipse.application=org.eclipse.jdt.ls.core.id1",
                "-Dosgi.bundles.defaultStartLevel=4",
                "-Declipse.product=org.eclipse.jdt.ls.core.product",
                "-Djava.import.generatesMetadataFilesAtProjectRoot=false",
                "-Dfile.encoding=utf8",
                "-noverify",
                "-XX:+UseParallelGC",
                "-XX:GCTimeRatio=4",
                "-XX:AdaptiveSizePolicyWeight=90",
                "-Dsun.zip.disableMemoryMapping=true",
                "-Djava.lsp.joinOnCompletion=true",
                "-Xmx3G",
                "-Xms100m",
                "-Xlog:disable",
                "-Dlog.level=ALL",
                f"-javaagent:{lombok_jar_path}",
                f"-Djdt.core.sharedIndexLocation={shared_cache_location}",
                "-jar",
                jdtls_launcher_jar,
                "-configuration",
                jdtls_config_path,
                "-data",
                data_dir,
            ]
        )

        self.service_ready_event = asyncio.Event()
        self.intellicode_enable_command_available = asyncio.Event()
        self.initialize_searcher_command_available = asyncio.Event()

        super().__init__(
            config, 
            initialize_params, 
            logger, 
            ProcessLaunchInfo(cmd, proc_env, proc_cwd), 
            Language.JAVA
        )

    def setupRuntimeDependencies(self, logger: MultilspyLogger, config: MultilspyConfig) -> RuntimeDependencyPaths:
        """
        Setup runtime dependencies for EclipseJDTLS.
        """
        platformId = PlatformUtils.get_platform_id()

        with open(str(PurePath(os.path.dirname(__file__), "runtime_dependencies.json")), "r") as f:
            runtimeDependencies = json.load(f)
            del runtimeDependencies["_description"]

        os.makedirs(str(PurePath(os.path.abspath(os.path.dirname(__file__)), "static")), exist_ok=True)

        assert platformId.value in [
            "linux-x64",
            "win-x64",
        ], "Only linux-x64 platform is supported for in multilspy at the moment"

        gradle_path = str(
            PurePath(
                os.path.abspath(os.path.dirname(__file__)),
                "static/gradle-7.3.3",
            )
        )

        if not os.path.exists(gradle_path):
            FileUtils.download_and_extract_archive(
                logger,
                runtimeDependencies["gradle"]["platform-agnostic"]["url"],
                str(PurePath(gradle_path).parent),
                runtimeDependencies["gradle"]["platform-agnostic"]["archiveType"],
            )

        assert os.path.exists(gradle_path)

        dependency = runtimeDependencies["vscode-java"][platformId.value]
        vscode_java_path = str(
            PurePath(os.path.abspath(os.path.dirname(__file__)), "static", dependency["relative_extraction_path"])
        )
        os.makedirs(vscode_java_path, exist_ok=True)
        jre_home_path = str(PurePath(vscode_java_path, dependency["jre_home_path"]))
        jre_path = str(PurePath(vscode_java_path, dependency["jre_path"]))
        lombok_jar_path = str(PurePath(vscode_java_path, dependency["lombok_jar_path"]))
        jdtls_launcher_jar_path = str(PurePath(vscode_java_path, dependency["jdtls_launcher_jar_path"]))
        jdtls_readonly_config_path = str(PurePath(vscode_java_path, dependency["jdtls_readonly_config_path"]))
        if not all(
            [
                os.path.exists(vscode_java_path),
                os.path.exists(jre_home_path),
                os.path.exists(jre_path),
                os.path.exists(lombok_jar_path),
                os.path.exists(jdtls_launcher_jar_path),
                os.path.exists(jdtls_readonly_config_path),
            ]
        ):
            FileUtils.download_and_extract_archive(
                logger, dependency["url"], vscode_java_path, dependency["archiveType"]
            )

        os.chmod(jre_path, stat.S_IEXEC)

        assert os.path.exists(vscode_java_path)
        assert os.path.exists(jre_home_path)
        assert os.path.exists(jre_path)
        assert os.path.exists(lombok_jar_path)
        assert os.path.exists(jdtls_launcher_jar_path)
        assert os.path.exists(jdtls_readonly_config_path)

        dependency = runtimeDependencies["intellicode"]["platform-agnostic"]
        intellicode_directory_path = str(
            PurePath(os.path.abspath(os.path.dirname(__file__)), "static", dependency["relative_extraction_path"])
        )
        os.makedirs(intellicode_directory_path, exist_ok=True)
        intellicode_jar_path = str(PurePath(intellicode_directory_path, dependency["intellicode_jar_path"]))
        intellisense_members_path = str(PurePath(intellicode_directory_path, dependency["intellisense_members_path"]))
        if not all(
            [
                os.path.exists(intellicode_directory_path),
                os.path.exists(intellicode_jar_path),
                os.path.exists(intellisense_members_path),
            ]
        ):
            FileUtils.download_and_extract_archive(
                logger, dependency["url"], intellicode_directory_path, dependency["archiveType"]
            )

        assert os.path.exists(intellicode_directory_path)
        assert os.path.exists(intellicode_jar_path)
        assert os.path.exists(intellisense_members_path)

        return RuntimeDependencyPaths(
            gradle_path=gradle_path,
            lombok_jar_path=lombok_jar_path,
            jre_path=jre_path,
            jre_home_path=jre_home_path,
            jdtls_launcher_jar_path=jdtls_launcher_jar_path,
            jdtls_readonly_config_path=jdtls_readonly_config_path,
            intellicode_jar_path=intellicode_jar_path,
            intellisense_members_path=intellisense_members_path,
        )

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["EclipseJDTLS"]:
        """
        Starts the Eclipse JDTLS Language Server, waits for the server to be ready and yields the LanguageServer instance.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and ready to serve requests
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown
        ```
        """

        async def register_capability_handler(params):
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "textDocument/completion":
                    assert registration["registerOptions"]["resolveProvider"] == True
                    assert registration["registerOptions"]["triggerCharacters"] == [
                        ".",
                        "@",
                        "#",
                        "*",
                        " ",
                    ]
                    self.completions_available.set()
                if registration["method"] == "workspace/executeCommand":
                    if "java.intellicode.enable" in registration["registerOptions"]["commands"]:
                        self.intellicode_enable_command_available.set()
            return

        async def lang_status_handler(params):
            # TODO: Should we wait for
            # server -> client: {'jsonrpc': '2.0', 'method': 'language/status', 'params': {'type': 'ProjectStatus', 'message': 'OK'}}
            # Before proceeding?
            if params["type"] == "ServiceReady" and params["message"] == "ServiceReady":
                self.service_ready_event.set()

        async def execute_client_command_handler(params):
            assert params["command"] == "_java.reloadBundles.command"
            assert params["arguments"] == []
            return []

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        async def do_nothing(params):
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)

        async with super().start_server():
            self.logger.log("Starting EclipseJDTLS server process", logging.INFO)
            await self.server.start()

            self.logger.log(
                "Sending initialize request from LSP client to LSP server and awaiting response",
                logging.INFO,
            )
            init_response = await self.server.send.initialize(self.initialize_params)
            assert init_response["capabilities"]["textDocumentSync"]["change"] == 2
            assert "completionProvider" not in init_response["capabilities"]
            assert "executeCommandProvider" not in init_response["capabilities"]

            self.server.notify.initialized({})

            self.server.notify.workspace_did_change_configuration(
                {"settings": self.initialize_params["initializationOptions"]["settings"]}
            )

            await self.intellicode_enable_command_available.wait()

            java_intellisense_members_path = self.runtime_dependency_paths.intellisense_members_path
            assert os.path.exists(java_intellisense_members_path)
            intellicode_enable_result = await self.server.send.execute_command(
                {
                    "command": "java.intellicode.enable",
                    "arguments": [True, java_intellisense_members_path],
                }
            )
            assert intellicode_enable_result

            # TODO: Add comments about why we wait here, and how this can be optimized
            await self.service_ready_event.wait()

            yield self

            await self.server.shutdown()
            await self.server.stop()
