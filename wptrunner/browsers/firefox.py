# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os

from mozprocess import ProcessHandler
from mozprofile import FirefoxProfile, Preferences
from mozprofile.permissions import ServerLocations
from mozrunner import FirefoxRunner

from .base import get_free_port, Browser, ExecutorBrowser, require_arg, cmd_arg
from ..executors import get_executor_kwargs as base_executor_kwargs
from ..executors.executormarionette import MarionetteTestharnessExecutor, MarionetteReftestExecutor, required_files

here = os.path.join(os.path.split(__file__)[0])

__wptrunner__ = {"product": "firefox",
                 "check_args": "check_args",
                 "browser": "FirefoxBrowser",
                 "executor": {"testharness": "MarionetteTestharnessExecutor",
                              "reftest": "MarionetteReftestExecutor"},
                 "browser_kwargs": "browser_kwargs",
                 "executor_kwargs": "get_executor_kwargs",
                 "env_options": "env_options"}


def check_args(**kwargs):
    require_arg(kwargs, "binary")


def browser_kwargs(**kwargs):
    return {"binary": kwargs["binary"],
            "prefs_root": kwargs["prefs_root"]}


def get_executor_kwargs(http_server_url, **kwargs):
    executor_kwargs = base_executor_kwargs(http_server_url, **kwargs)
    executor_kwargs["close_after_done"] = True
    return executor_kwargs


def env_options():
    return {"host": "localhost",
            "bind_hostname": "true",
            "required_files": required_files}


class FirefoxBrowser(Browser):
    used_ports = set()

    def __init__(self, logger, binary, prefs_root):
        Browser.__init__(self, logger)
        self.binary = binary
        self.prefs_root = prefs_root
        self.marionette_port = get_free_port(2828, exclude=self.used_ports)
        self.used_ports.add(self.marionette_port)
        self.runner = None

    def start(self):
        env = os.environ.copy()
        env['MOZ_CRASHREPORTER_NO_REPORT'] = '1'
        env["MOZ_DISABLE_NONLOCAL_CONNECTIONS"] = "1"

        locations = ServerLocations(filename=os.path.join(here, "server-locations.txt"))

        preferences = self.load_prefs()

        profile = FirefoxProfile(locations=locations, proxy=True, preferences=preferences)
        profile.set_preferences({"marionette.defaultPrefs.enabled": True,
                                 "marionette.defaultPrefs.port": self.marionette_port,
                                 "dom.disable_open_during_load": False})

        self.runner = FirefoxRunner(profile,
                                    self.binary,
                                    cmdargs=[cmd_arg("marionette"), "about:blank"],
                                    env=env,
                                    kp_kwargs={"processOutputLine": [self.on_output]},
                                    process_class=ProcessHandler)

        self.logger.debug("Starting Firefox")
        self.runner.start()
        self.logger.debug("Firefox Started")

    def load_prefs(self):
        prefs_path = os.path.join(self.prefs_root, "prefs_general.js")
        if os.path.exists(prefs_path):
            preferences = Preferences.read_prefs(prefs_path)
        else:
            self.logger.warning("Failed to find base prefs file in %s" % prefs_path)
            preferences = []

        return preferences

    def stop(self):
        self.logger.debug("Stopping browser")
        if self.runner is not None:
            try:
                self.runner.stop()
            except OSError:
                # This can happen on Windows if the process is already dead
                pass

    def pid(self):
        if self.runner.process_handler is not None:
            try:
                pid = self.runner.process_handler.pid
            except AttributeError:
                pid = None
        else:
            pid = None
        return pid

    def on_output(self, line):
        """Write a line of output from the firefox process to the log"""
        self.logger.process_output(self.pid(),
                                   line.decode("utf8"),
                                   command=" ".join(self.runner.command))

    def is_alive(self):
        return self.runner.is_running()

    def cleanup(self):
        self.stop()

    def executor_browser(self):
        return ExecutorBrowser, {"marionette_port": self.marionette_port}
