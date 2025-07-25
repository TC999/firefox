#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
"""Python usage, esp. virtualenv.
"""

import errno
import json
import os
import shutil
import site
import socket
import subprocess
import sys
import traceback
from pathlib import Path

try:
    import urlparse
except ImportError:
    import urllib.parse as urlparse


import mozharness
from mozharness.base.errors import VirtualenvErrorList
from mozharness.base.log import FATAL, WARNING
from mozharness.base.script import (
    PostScriptAction,
    PostScriptRun,
    PreScriptAction,
    ScriptMixin,
)

external_tools_path = os.path.join(
    os.path.abspath(os.path.dirname(os.path.dirname(mozharness.__file__))),
    "external_tools",
)


class MultipleWheelMatchError(Exception):
    pass


def get_uv_executable():
    return shutil.which("uv")


def pip_command(*, python_executable, subcommand=None, args=None, non_uv_args=None):
    if uv_executable := get_uv_executable():
        command = [uv_executable, "pip"]
        if subcommand:
            command.append(subcommand)
            python_root = Path(python_executable).parent.parent
            command.append(f"--python={python_root}")
        full_command = command + (args or [])
    else:
        command = [python_executable, "-m", "pip"]
        if subcommand:
            command.append(subcommand)
        full_command = command + (non_uv_args or []) + (args or [])

    return full_command


def get_tlsv1_post():
    # Monkeypatch to work around SSL errors in non-bleeding-edge Python.
    # Taken from https://lukasa.co.uk/2013/01/Choosing_SSL_Version_In_Requests/
    import ssl

    import requests
    from requests.packages.urllib3.poolmanager import PoolManager

    class TLSV1Adapter(requests.adapters.HTTPAdapter):
        def init_poolmanager(self, connections, maxsize, block=False):
            self.poolmanager = PoolManager(
                num_pools=connections,
                maxsize=maxsize,
                block=block,
                ssl_version=ssl.PROTOCOL_TLSv1,
            )

    s = requests.Session()
    s.mount("https://", TLSV1Adapter())
    return s.post


# Virtualenv {{{1
virtualenv_config_options = [
    [
        ["--virtualenv-path"],
        {
            "action": "store",
            "dest": "virtualenv_path",
            "default": "venv",
            "help": "Specify the path to the virtualenv top level directory",
        },
    ],
    [
        ["--find-links"],
        {
            "action": "extend",
            "dest": "find_links",
            "default": ["https://pypi.pub.build.mozilla.org/pub/"],
            "help": "URL to look for packages at",
        },
    ],
    [
        ["--pip-index"],
        {
            "action": "store_true",
            "default": False,
            "dest": "pip_index",
            "help": "Use pip indexes",
        },
    ],
    [
        ["--no-pip-index"],
        {
            "action": "store_false",
            "dest": "pip_index",
            "help": "Don't use pip indexes (default)",
        },
    ],
]


class VirtualenvMixin:
    """BaseScript mixin, designed to create and use virtualenvs.

    Config items:
     * virtualenv_path points to the virtualenv location on disk.
     * virtualenv_modules lists the module names.
     * MODULE_url list points to the module URLs (optional)
    Requires virtualenv to be in PATH.
    Depends on ScriptMixin
    """

    python_paths = {}
    site_packages_path = None

    def __init__(self, *args, **kwargs):
        self._virtualenv_modules = []
        super(VirtualenvMixin, self).__init__(*args, **kwargs)

    def register_virtualenv_module(
        self,
        name=None,
        url=None,
        method=None,
        requirements=None,
        optional=False,
        editable=False,
    ):
        """Register a module to be installed with the virtualenv.

        This method can be called up until create_virtualenv() to register
        modules that should be installed in the virtualenv.

        See the documentation for install_module for how the arguments are
        applied.
        """
        self._virtualenv_modules.append(
            (name, url, method, requirements, optional, editable)
        )

    def query_virtualenv_path(self):
        """Determine the absolute path to the virtualenv."""
        dirs = self.query_abs_dirs()

        if "abs_virtualenv_dir" in dirs:
            return dirs["abs_virtualenv_dir"]

        p = self.config["virtualenv_path"]
        if not p:
            self.fatal(
                "virtualenv_path config option not set; " "this should never happen"
            )

        if os.path.isabs(p):
            return p
        else:
            return os.path.join(dirs["abs_work_dir"], p)

    def query_python_path(self, binary="python"):
        """Return the path of a binary inside the virtualenv, if
        c['virtualenv_path'] is set; otherwise return the binary name.
        Otherwise return None
        """
        if binary not in self.python_paths:
            bin_dir = "bin"
            if self._is_windows():
                bin_dir = "Scripts"
            virtualenv_path = self.query_virtualenv_path()
            self.python_paths[binary] = os.path.abspath(
                os.path.join(virtualenv_path, bin_dir, binary)
            )

        return self.python_paths[binary]

    def query_python_site_packages_path(self):
        if self.site_packages_path:
            return self.site_packages_path
        python = self.query_python_path()
        self.site_packages_path = self.get_output_from_command(
            [
                python,
                "-c",
                "from sysconfig; print(sysconfig.get_paths()['purelib'])",
            ]
        )
        return self.site_packages_path

    def package_versions(
        self, pip_freeze_output=None, error_level=WARNING, log_output=False
    ):
        """
        reads packages from `pip freeze` output and returns a dict of
        {package_name: 'version'}
        """
        packages = {}

        if pip_freeze_output is None:
            # get the output from `pip freeze`
            pip = self.query_python_path("pip")
            if not pip:
                self.log("package_versions: Program pip not in path", level=error_level)
                return {}
            pip_list_command = pip_command(
                python_executable=self.query_python_path(),
                subcommand="list",
                args=["--format", "freeze", "--no-index"],
            )
            pip_freeze_output = self.get_output_from_command(
                pip_list_command,
                silent=True,
                ignore_errors=True,
            )
            if not isinstance(pip_freeze_output, str):
                self.fatal(
                    f"package_versions: Error encountered running `pip freeze`: {pip_freeze_output}"
                )

        for l in pip_freeze_output.splitlines():
            # parse the output into package, version
            line = l.strip()
            if not line:
                # whitespace
                continue
            if line.startswith("-"):
                # not a package, probably like '-e http://example.com/path#egg=package-dev'
                continue
            if "==" not in line:
                self.fatal("pip_freeze_packages: Unrecognized output line: %s" % line)
            package, version = line.split("==", 1)
            packages[package] = version

        if log_output:
            self.info("Current package versions:")
            for package in sorted(packages):
                self.info("  %s == %s" % (package, packages[package]))

        return packages

    def is_python_package_installed(self, package_name, error_level=WARNING):
        """
        Return whether the package is installed
        """
        # pylint --py3k W1655
        package_versions = self.package_versions(error_level=error_level)
        return package_name.lower() in [package.lower() for package in package_versions]

    def install_module(
        self,
        module=None,
        module_url=None,
        install_method=None,
        requirements=(),
        optional=False,
        global_options=[],
        no_deps=False,
        editable=False,
    ):
        """
        Install module via pip.

        module_url can be a url to a python package tarball, a path to
        a directory containing a setup.py (absolute or relative to work_dir)
        or None, in which case it will default to the module name.

        requirements is a list of pip requirements files.  If specified, these
        will be combined with the module_url (if any), like so:

        pip install -r requirements1.txt -r requirements2.txt module_url
        """
        import http.client
        import time
        import urllib.error
        import urllib.request

        c = self.config
        dirs = self.query_abs_dirs()
        env = self.query_env()
        venv_path = self.query_virtualenv_path()
        self.info("Installing %s into virtualenv %s" % (module, venv_path))
        if not module_url:
            module_url = module
        if install_method in (None, "pip"):
            if not module_url and not requirements:
                self.fatal("Must specify module and/or requirements")
            pip_command_args = []
            pip_command_non_uv_args = []
            if c.get("verbose_pip"):
                pip_command_args += ["-v"]
            if no_deps:
                pip_command_args += ["--no-deps"]

            pip_command_non_uv_args += ["--no-use-pep517"]

            # To avoid timeouts with our pypi server, increase default timeout:
            # https://bugzilla.mozilla.org/show_bug.cgi?id=1007230#c802
            pip_command_non_uv_args += ["--timeout", str(c.get("pip_timeout", 120))]
            for requirement in requirements:
                pip_command_args += ["-r", requirement]
            if c.get("find_links") and not c["pip_index"]:
                pip_command_args += ["--no-index"]
            for opt in global_options:
                pip_command_args += ["--global-option", opt]
        else:
            self.fatal(
                "install_module() doesn't understand an install_method of %s!"
                % install_method
            )

        # find_links connection check while loop
        find_links_added = 0
        fl_retry_sleep_seconds = 10
        fl_max_retry_minutes = 5
        fl_retry_loops = (fl_max_retry_minutes * 60) / fl_retry_sleep_seconds
        for link in c.get("find_links", []):
            parsed = urlparse.urlparse(link)
            if parsed.scheme in ["http", "https"]:
                dns_result = None
                get_result = None
                retry_counter = 0
                while retry_counter < fl_retry_loops and (
                    dns_result is None or get_result is None
                ):
                    try:
                        dns_result = socket.gethostbyname(parsed.hostname)
                        get_result = urllib.request.urlopen(link, timeout=10).read()
                        break
                    except socket.gaierror:
                        retry_counter += 1
                        self.warning(
                            "find_links: dns check failed for %s, sleeping %ss and retrying..."
                            % (parsed.hostname, fl_retry_sleep_seconds)
                        )
                        time.sleep(fl_retry_sleep_seconds)
                    except (
                        urllib.error.HTTPError,
                        urllib.error.URLError,
                        socket.timeout,
                        http.client.RemoteDisconnected,
                    ) as e:
                        retry_counter += 1
                        self.warning(
                            "find_links: connection check failed for %s, sleeping %ss and retrying..."
                            % (link, fl_retry_sleep_seconds)
                        )
                        self.warning("find_links: exception: %s" % e)
                        time.sleep(fl_retry_sleep_seconds)
                # now that the connectivity check is good, add the link
                if dns_result and get_result:
                    self.info(
                        "find_links: connection checks passed for %s, adding." % link
                    )
                    find_links_added += 1
                    pip_command_args.extend(["--find-links", link])
                else:
                    self.warning(
                        "find_links: connection checks failed for %s"
                        ", but max retries reached. continuing..." % link
                    )
            elif len(parsed.path) > 0 and os.path.isdir(link):
                self.info("find_links: dir exists %s, adding." % link)
                find_links_added += 1
                pip_command_args.extend(["--find-links", link])
            else:
                self.warning("find_links: not a valid path nor URL %s" % link)

        # TODO: make this fatal if we always see failures after this
        if find_links_added == 0:
            self.warning(
                "find_links: no find_links added. pip installation will probably fail!"
            )

        # module_url can be None if only specifying requirements files
        if module_url:
            if editable:
                if install_method in (None, "pip"):
                    pip_command_args += ["-e"]
                else:
                    self.fatal(
                        "editable installs not supported for install_method %s"
                        % install_method
                    )
            pip_command_args += [module_url]

        # If we're only installing a single requirements file, use
        # the file's directory as cwd, so relative paths work correctly.
        cwd = dirs["abs_work_dir"]
        if not module and len(requirements) == 1:
            cwd = os.path.dirname(requirements[0])

        pip_install_command = (
            pip_command(
                python_executable=self.query_python_path(),
                subcommand="install",
                args=pip_command_args,
                non_uv_args=pip_command_non_uv_args,
            ),
        )

        # Allow for errors while building modules, but require a
        # return status of 0.
        self.retry(
            self.run_command,
            # None will cause default value to be used
            attempts=1 if optional else None,
            good_statuses=(0,),
            error_level=WARNING if optional else FATAL,
            error_message="Could not install python package: failed all attempts.",
            args=pip_install_command,
            kwargs={
                "error_list": VirtualenvErrorList,
                "cwd": cwd,
                "env": env,
                # WARNING only since retry will raise final FATAL if all
                # retry attempts are unsuccessful - and we only want
                # an ERROR of FATAL if *no* retry attempt works
                "error_level": WARNING,
            },
        )

    def create_virtualenv(self, modules=(), requirements=()):
        """
        Create a python virtualenv.

        This uses the copy of virtualenv that is vendored in mozharness.

        virtualenv_modules can be a list of module names to install, e.g.

            virtualenv_modules = ['module1', 'module2']

        or it can be a heterogeneous list of modules names and dicts that
        define a module by its name, url-or-path, and a list of its global
        options.

            virtualenv_modules = [
                {
                    'name': 'module1',
                    'url': None,
                    'global_options': ['--opt', '--without-gcc']
                },
                {
                    'name': 'module2',
                    'url': 'http://url/to/package',
                    'global_options': ['--use-clang']
                },
                {
                    'name': 'module3',
                    'url': os.path.join('path', 'to', 'setup_py', 'dir')
                    'global_options': []
                },
                'module4'
            ]

        virtualenv_requirements is an optional list of pip requirements files to
        use when invoking pip, e.g.,

            virtualenv_requirements = [
                '/path/to/requirements1.txt',
                '/path/to/requirements2.txt'
            ]
        """
        c = self.config
        dirs = self.query_abs_dirs()
        venv_path = self.query_virtualenv_path()
        self.info(f"Creating virtualenv {venv_path}")
        self.mkdir_p(dirs["abs_work_dir"])

        # Always use the virtualenv that is vendored since that is deterministic.
        # base_work_dir is for when we're running with mozharness.zip, e.g. on
        # test jobs
        # abs_src_dir is for when we're running out of a checked out copy of
        # the source code
        vendor_search_dirs = [
            os.path.join("{base_work_dir}", "mozharness"),
            "{abs_src_dir}",
        ]
        if "abs_src_dir" not in dirs and "repo_path" in self.config:
            dirs["abs_src_dir"] = os.path.normpath(self.config["repo_path"])

        wheels = {}

        for d in vendor_search_dirs:
            try:
                src_dir = Path(d.format(**dirs))
            except KeyError:
                continue

            src_dir_wheels_path = (
                src_dir / "third_party" / "python" / "_venv" / "wheels"
            )
            wheel_patterns = {
                "wheel": "wheel*.whl",
                "pip": "pip*.whl",
                "setuptools": "setuptools*.whl",
            }
            wheel_matches = {}
            multi_match_errors = []

            for key, pattern in wheel_patterns.items():
                files = list(src_dir_wheels_path.glob(pattern))
                num_matches = len(files)
                if num_matches > 1:
                    multi_match_errors.append(
                        f"{num_matches} wheels for '{key}' were found."
                    )
                elif num_matches == 1:
                    wheel_matches[key] = files[0]

            if multi_match_errors:
                error_message = (
                    "Found multiple matches for wheels of the same package. "
                    "Please ensure that only a single wheel is vendored for each:\n"
                    + "\n".join(multi_match_errors)
                )
                raise MultipleWheelMatchError(error_message)

            # At this point, we've errored out if there's more than one match for a specific wheel.
            # So if every wheel has a single match, we're done and can break out. If we didn't match
            # all the wheels we expect, continue searching in another directory.
            if set(wheel_patterns.keys()) == set(wheel_matches.keys()):
                wheels = wheel_matches
                break
        else:
            self.fatal("Can't find all of 'pip', 'setuptools', and 'wheel' wheels.")

        venv_python_bin = Path(self.query_python_path())

        if venv_python_bin.exists():
            self.info(
                "Virtualenv %s appears to already exist; "
                "skipping virtualenv creation." % self.query_python_path()
            )
        else:
            self.run_command(
                [sys.executable, "--version"],
            )

            if uv_executable := get_uv_executable():
                self.run_command([uv_executable, "--version"])

                # MOZ_PYTHON_HOME is only set in CI, but this code can execute locally for testing
                # (e.g.: `./mach raptor`), so let's fall back to the sys.executable path in that case.
                python_path = os.environ.get(
                    "MOZ_PYTHON_HOME", Path(sys.executable).parents[1]
                )
                uv_venv_creation_command = [
                    "uv",
                    "venv",
                    venv_path,
                    "--relocatable",
                    f"--python={python_path}",
                    "--no-project",
                ]
                self.run_command(
                    uv_venv_creation_command,
                    cwd=dirs["abs_work_dir"],
                    error_list=VirtualenvErrorList,
                    halt_on_failure=True,
                )
            else:
                venv_creation_flags = ["-m", "venv", venv_path]

                if self._is_windows():
                    # To workaround an issue on Windows10 jobs in CI we have to
                    # explicitly install the default pip separately. Ideally we
                    # could just remove the "--without-pip" above and get the same
                    # result, but that's apparently not always the case.
                    venv_creation_flags = venv_creation_flags + ["--without-pip"]

                self.run_command(
                    [sys.executable] + venv_creation_flags,
                    cwd=dirs["abs_work_dir"],
                    error_list=VirtualenvErrorList,
                    halt_on_failure=True,
                )

                if self._is_windows():
                    self.run_command(
                        [str(venv_python_bin), "-m", "ensurepip", "--default-pip"],
                        cwd=dirs["abs_work_dir"],
                        halt_on_failure=True,
                    )

            self._ensure_python_exe(venv_python_bin.parent)

            pip_install_command = pip_command(
                python_executable=str(venv_python_bin),
                subcommand="install",
                args=[
                    "--only-binary",
                    ":all:",
                    "--disable-pip-version-check",
                    str(wheels["pip"]),
                    str(wheels["setuptools"]),
                    str(wheels["wheel"]),
                ],
            )

            self.run_command(
                pip_install_command,
                cwd=dirs["abs_work_dir"],
                error_list=VirtualenvErrorList,
                halt_on_failure=True,
            )

        self.info(self.platform_name())
        if self.platform_name().startswith("macos"):
            tmp_path = f"{venv_path}/bin/bak"
            self.info(
                f"Copying venv python binaries to {tmp_path} to clear for re-sign"
            )
            subprocess.call(f"mkdir -p {tmp_path}", shell=True)
            subprocess.call(f"cp {venv_path}/bin/python* {tmp_path}/", shell=True)
            self.info("Replacing venv python binaries with reset copies")
            subprocess.call(f"mv -f {tmp_path}/* {venv_path}/bin/", shell=True)
            self.info(
                "codesign -s - --preserve-metadata=identifier,entitlements,flags,runtime "
                f"-f {venv_path}/bin/*"
            )
            subprocess.call(
                "codesign -s - --preserve-metadata=identifier,entitlements,flags,runtime -f "
                f"{venv_path}/bin/python*",
                shell=True,
            )

        if not modules:
            modules = c.get("virtualenv_modules", [])
        if not requirements:
            requirements = c.get("virtualenv_requirements", [])
        if not modules and requirements:
            self.install_module(requirements=requirements, install_method="pip")
        for module in modules:
            module_url = module
            global_options = []
            if isinstance(module, dict):
                if module.get("name", None):
                    module_name = module["name"]
                else:
                    self.fatal(
                        "Can't install module without module name: %s" % str(module)
                    )
                module_url = module.get("url", None)
                global_options = module.get("global_options", [])
            else:
                module_url = self.config.get("%s_url" % module, module_url)
                module_name = module
            install_method = "pip"
            self.install_module(
                module=module_name,
                module_url=module_url,
                install_method=install_method,
                requirements=requirements,
                global_options=global_options,
            )

        for (
            module,
            url,
            method,
            requirements,
            optional,
            editable,
        ) in self._virtualenv_modules:
            self.install_module(
                module=module,
                module_url=url,
                install_method=method,
                requirements=requirements or (),
                optional=optional,
                editable=editable,
            )

        self.info("Done creating virtualenv %s." % venv_path)

        self.package_versions(log_output=True)

    def activate_virtualenv(self):
        """Import the virtualenv's packages into this Python interpreter."""
        venv_root_dir = Path(self.query_virtualenv_path())
        bin_path = Path(self.query_python_path())
        bin_dir = bin_path.parent

        if self._is_windows():
            site_packages_dir = venv_root_dir / "Lib" / "site-packages"
        else:
            site_packages_dir = (
                venv_root_dir
                / "lib"
                / "python{}.{}".format(*sys.version_info)
                / "site-packages"
            )

        os.environ["PATH"] = os.pathsep.join(
            [str(bin_dir)] + os.environ.get("PATH", "").split(os.pathsep)
        )

        os.environ["VIRTUAL_ENV"] = str(venv_root_dir)

        prev_path = set(sys.path)

        site.addsitedir(str(site_packages_dir.resolve()))

        new_path = list(sys.path)

        sys.path[:] = [p for p in new_path if p not in prev_path] + [
            p for p in new_path if p in prev_path
        ]

        sys.real_prefix = sys.prefix
        sys.prefix = str(venv_root_dir)
        sys.executable = str(bin_path)

    def _ensure_python_exe(self, python_exe_root: Path):
        """On some machines in CI venv does not behave consistently. Sometimes
        only a "python3" executable is created, but we expect "python". Since
        they are functionally identical, we can just copy "python3" to "python"
        (and vice-versa) to solve the problem.
        """
        python3_exe_path = python_exe_root / "python3"
        python_exe_path = python_exe_root / "python"

        if self._is_windows():
            python3_exe_path = python3_exe_path.with_suffix(".exe")
            python_exe_path = python_exe_path.with_suffix(".exe")

        if python3_exe_path.exists() and not python_exe_path.exists():
            shutil.copy(str(python3_exe_path), str(python_exe_path))

        if python_exe_path.exists() and not python3_exe_path.exists():
            shutil.copy(str(python_exe_path), str(python3_exe_path))

        if not python_exe_path.exists() and not python3_exe_path.exists():
            raise Exception(
                f'Neither a "{python_exe_path.name}" or "{python3_exe_path.name}" '
                f"were found. This means something unexpected happened during the "
                f"virtual environment creation and we cannot proceed."
            )


# This is (sadly) a mixin for logging methods.
class PerfherderResourceOptionsMixin(ScriptMixin):
    def perfherder_resource_options(self):
        """Obtain a list of extraOptions values to identify the env."""
        opts = []

        if "TASKCLUSTER_INSTANCE_TYPE" in os.environ:
            # Include the instance type so results can be grouped.
            opts.append("taskcluster-%s" % os.environ["TASKCLUSTER_INSTANCE_TYPE"])
        else:
            # We assume !taskcluster => buildbot.
            instance = "unknown"

            # Try to load EC2 instance type from metadata file. This file
            # may not exist in many scenarios (including when inside a chroot).
            # So treat it as optional.
            try:
                # This file should exist on Linux in EC2.
                with open("/etc/instance_metadata.json", "rb") as fh:
                    im = json.load(fh)
                    instance = im.get("aws_instance_type", "unknown").encode("ascii")
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise
                self.info(
                    "instance_metadata.json not found; unable to "
                    "determine instance type"
                )
            except Exception:
                self.warning(
                    "error reading instance_metadata: %s" % traceback.format_exc()
                )

            opts.append("buildbot-%s" % instance)

        return opts


class ResourceMonitoringMixin(PerfherderResourceOptionsMixin):
    """Provides resource monitoring capabilities to scripts.

    When this class is in the inheritance chain, resource usage stats of the
    executing script will be recorded.

    This class requires the VirtualenvMixin in order to install a package used
    for recording resource usage.

    While we would like to record resource usage for the entirety of a script,
    since we require an external package, we can only record resource usage
    after that package is installed (as part of creating the virtualenv).
    That's just the way things have to be.
    """

    def __init__(self, *args, **kwargs):
        super(ResourceMonitoringMixin, self).__init__(*args, **kwargs)

        self.register_virtualenv_module("psutil>=5.9.0", method="pip", optional=True)
        self.register_virtualenv_module("jsonschema==2.5.1", method="pip")
        self._resource_monitor = None

        # 2-tuple of (name, options) to assign Perfherder resource monitor
        # metrics to. This needs to be assigned by a script in order for
        # Perfherder metrics to be reported.
        self.resource_monitor_perfherder_id = None

    @PostScriptAction("create-virtualenv")
    def _start_resource_monitoring(self, action, success=None):
        self.activate_virtualenv()

        try:
            from mozsystemmonitor.resourcemonitor import SystemResourceMonitor

            self.info("Starting resource monitoring.")
            metadata = {}
            if "TASKCLUSTER_WORKER_TYPE" in os.environ:
                metadata["device"] = os.environ["TASKCLUSTER_WORKER_TYPE"]
            if "MOZHARNESS_TEST_PATHS" in os.environ:
                metadata["product"] = " ".join(
                    json.loads(os.environ["MOZHARNESS_TEST_PATHS"]).keys()
                )
            if "MOZ_SOURCE_CHANGESET" in os.environ and "MOZ_SOURCE_REPO" in os.environ:
                metadata["sourceURL"] = (
                    os.environ["MOZ_SOURCE_REPO"]
                    + "/rev/"
                    + os.environ["MOZ_SOURCE_CHANGESET"]
                )
            if "TASK_ID" in os.environ:
                metadata["appBuildID"] = os.environ["TASK_ID"]
            self._resource_monitor = SystemResourceMonitor(
                poll_interval=0.1, metadata=metadata
            )
            self._resource_monitor.start()
        except Exception:
            self.warning(
                "Unable to start resource monitor: %s" % traceback.format_exc()
            )

    @PreScriptAction
    def _resource_record_pre_action(self, action):
        # Resource monitor isn't available until after create-virtualenv.
        if not self._resource_monitor:
            return

        self._resource_monitor.begin_phase(action)

    @PostScriptAction
    def _resource_record_post_action(self, action, success=None):
        # Resource monitor isn't available until after create-virtualenv.
        if not self._resource_monitor:
            return

        self._resource_monitor.finish_phase(action)

    @PostScriptRun
    def _resource_record_post_run(self):
        if not self._resource_monitor:
            return

        self._resource_monitor.stop()
        self._log_resource_usage()

        # Upload a JSON file containing the raw resource data.
        try:
            upload_dir = self.query_abs_dirs()["abs_blob_upload_dir"]
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)
            with open(os.path.join(upload_dir, "resource-usage.json"), "w") as fh:
                json.dump(
                    self._resource_monitor.as_dict(), fh, sort_keys=True, indent=4
                )
            with open(
                os.path.join(upload_dir, "profile_resource-usage.json"), "w"
            ) as fh:
                json.dump(
                    self._resource_monitor.as_profile(),
                    fh,
                    separators=(",", ":"),
                )
        except (AttributeError, KeyError):
            self.exception("could not upload resource usage JSON", level=WARNING)

    def _log_resource_usage(self):
        # Delay import because not available until virtualenv is populated.
        import jsonschema

        rm = self._resource_monitor

        if rm.start_time is None:
            return

        def resources(phase):
            cpu_percent = rm.aggregate_cpu_percent(phase=phase, per_cpu=False)
            cpu_times = rm.aggregate_cpu_times(phase=phase, per_cpu=False)
            io = rm.aggregate_io(phase=phase)

            swap_in = sum(m.swap.sin for m in rm.measurements)
            swap_out = sum(m.swap.sout for m in rm.measurements)

            return cpu_percent, cpu_times, io, (swap_in, swap_out)

        def log_usage(prefix, duration, cpu_percent, cpu_times, io):
            message = (
                "{prefix} - Wall time: {duration:.0f}s; "
                "CPU: {cpu_percent}; "
                "Read bytes: {io_read_bytes}; Write bytes: {io_write_bytes}; "
                "Read time: {io_read_time}; Write time: {io_write_time}"
            )

            # XXX Some test harnesses are complaining about a string being
            # being fed into a 'f' formatter. This will help diagnose the
            # issue.
            if cpu_percent:
                # pylint: disable=W1633
                cpu_percent_str = str(round(cpu_percent)) + "%"
            else:
                cpu_percent_str = "Can't collect data"

            try:
                self.info(
                    message.format(
                        prefix=prefix,
                        duration=duration,
                        cpu_percent=cpu_percent_str,
                        io_read_bytes=io.read_bytes,
                        io_write_bytes=io.write_bytes,
                        io_read_time=io.read_time,
                        io_write_time=io.write_time,
                    )
                )

            except ValueError:
                self.warning("Exception when formatting: %s" % traceback.format_exc())

        cpu_percent, cpu_times, io, (swap_in, swap_out) = resources(None)
        duration = rm.end_time - rm.start_time

        # Write out Perfherder data if configured.
        if self.resource_monitor_perfherder_id:
            perfherder_name, perfherder_options = self.resource_monitor_perfherder_id

            suites = []
            overall = []

            if cpu_percent:
                overall.append(
                    {
                        "name": "cpu_percent",
                        "value": cpu_percent,
                    }
                )

            overall.extend(
                [
                    {"name": "io_write_bytes", "value": io.write_bytes},
                    {"name": "io.read_bytes", "value": io.read_bytes},
                    {"name": "io_write_time", "value": io.write_time},
                    {"name": "io_read_time", "value": io.read_time},
                ]
            )

            suites.append(
                {
                    "name": "%s.overall" % perfherder_name,
                    "extraOptions": perfherder_options
                    + self.perfherder_resource_options(),
                    "subtests": overall,
                }
            )

            for phase in rm.phases.keys():
                phase_duration = rm.phases[phase][1] - rm.phases[phase][0]
                subtests = [
                    {
                        "name": "time",
                        "value": phase_duration,
                    }
                ]
                cpu_percent = rm.aggregate_cpu_percent(phase=phase, per_cpu=False)
                if cpu_percent is not None:
                    subtests.append(
                        {
                            "name": "cpu_percent",
                            "value": rm.aggregate_cpu_percent(
                                phase=phase, per_cpu=False
                            ),
                        }
                    )

                # We don't report I/O during each step because measured I/O
                # is system I/O and that I/O can be delayed (e.g. writes will
                # buffer before being flushed and recorded in our metrics).
                suites.append(
                    {
                        "name": "%s.%s" % (perfherder_name, phase),
                        "subtests": subtests,
                    }
                )

            data = {
                "framework": {"name": "job_resource_usage"},
                "suites": suites,
            }

            schema_path = os.path.join(
                external_tools_path, "performance-artifact-schema.json"
            )
            with open(schema_path, "rb") as fh:
                schema = json.load(fh)

            # this will throw an exception that causes the job to fail if the
            # perfherder data is not valid -- please don't change this
            # behaviour, otherwise people will inadvertently break this
            # functionality
            self.info("Validating Perfherder data against %s" % schema_path)
            jsonschema.validate(data, schema)
            self.info("PERFHERDER_DATA: %s" % json.dumps(data))

        log_usage("Total resource usage", duration, cpu_percent, cpu_times, io)

        # Print special messages so usage shows up in Treeherder.
        if cpu_percent:
            self._tinderbox_print(f"CPU usage<br/>{cpu_percent:,.1f}%")

        self._tinderbox_print(
            f"I/O read bytes / time<br/>{io.read_bytes:,} / {io.read_time:,}"
        )
        self._tinderbox_print(
            f"I/O write bytes / time<br/>{io.write_bytes:,} / {io.write_time:,}"
        )

        # Print CPU components having >1%. "cpu_times" is a data structure
        # whose attributes are measurements. Ideally we'd have an API that
        # returned just the measurements as a dict or something.
        cpu_attrs = []
        for attr in sorted(dir(cpu_times)):
            if attr.startswith("_"):
                continue
            if attr in ("count", "index"):
                continue
            cpu_attrs.append(attr)

        cpu_total = sum(getattr(cpu_times, attr) for attr in cpu_attrs)

        for attr in cpu_attrs:
            value = getattr(cpu_times, attr)
            # cpu_total can be 0.0. Guard against division by 0.
            # pylint --py3k W1619
            percent = value / cpu_total * 100.0 if cpu_total else 0.0

            if percent > 1.00:
                self._tinderbox_print(f"CPU {attr}<br/>{value:,.1f} ({percent:,.1f}%)")

        # Swap on Windows isn't reported by psutil.
        if not self._is_windows():
            self._tinderbox_print(f"Swap in / out<br/>{swap_in:,} / {swap_out:,}")

        for phase in rm.phases.keys():
            start_time, end_time = rm.phases[phase]
            cpu_percent, cpu_times, io, swap = resources(phase)
            log_usage(phase, end_time - start_time, cpu_percent, cpu_times, io)

    def _tinderbox_print(self, message):
        self.info("TinderboxPrint: %s" % message)


# This needs to be inherited only if you have already inherited ScriptMixin
class Python3Virtualenv:
    """Support Python3.5+ virtualenv creation."""

    py3_initialized_venv = False

    def py3_venv_configuration(self, python_path, venv_path):
        """We don't use __init__ to allow integrating with other mixins.

        python_path - Path to Python 3 binary.
        venv_path - Path to virtual environment to be created.
        """
        self.py3_initialized_venv = True
        self.py3_python_path = os.path.abspath(python_path)
        version = self.get_output_from_command(
            [self.py3_python_path, "--version"], env=self.query_env()
        ).split()[-1]
        # Using -m venv is only used on 3.5+ versions
        assert version > "3.5.0"
        self.py3_venv_path = os.path.abspath(venv_path)
        self.py3_pip_path = os.path.join(self.py3_path_to_executables(), "pip")

    def py3_path_to_executables(self):
        platform = self.platform_name()
        if platform.startswith("win"):
            return os.path.join(self.py3_venv_path, "Scripts")
        else:
            return os.path.join(self.py3_venv_path, "bin")

    def py3_venv_initialized(func):
        def call(self, *args, **kwargs):
            if not self.py3_initialized_venv:
                raise Exception(
                    "You need to call py3_venv_configuration() "
                    "before using this method."
                )
            func(self, *args, **kwargs)

        return call

    @py3_venv_initialized
    def py3_create_venv(self):
        """Create Python environment with python3 -m venv /path/to/venv."""
        if os.path.exists(self.py3_venv_path):
            self.info(
                "Virtualenv %s appears to already exist; skipping "
                "virtualenv creation." % self.py3_venv_path
            )
        else:
            self.info("Running command...")
            self.run_command(
                "%s -m venv %s" % (self.py3_python_path, self.py3_venv_path),
                error_list=VirtualenvErrorList,
                halt_on_failure=True,
                env=self.query_env(),
            )

    @py3_venv_initialized
    def py3_install_modules(self, modules, use_mozharness_pip_config=True):
        if not os.path.exists(self.py3_venv_path):
            raise Exception("You need to call py3_create_venv() first.")

        for m in modules:
            pip_install_command_args = []
            pip_install_non_uv_args = []
            if use_mozharness_pip_config:
                pip_args, pip_install_non_uv_args = self._mozharness_pip_args()
                pip_install_command_args += pip_args
            pip_install_command_args += [m]

            pip_install_command = (
                pip_command(
                    python_executable=self.py3_python_path,
                    subcommand="install",
                    args=pip_install_command_args,
                    non_uv_args=pip_install_non_uv_args,
                ),
            )
            self.run_command(pip_install_command, env=self.query_env())

    def _mozharness_pip_args(self):
        """We have information in Mozharness configs that apply to pip"""
        c = self.config
        pip_args = []
        # To avoid timeouts with our pypi server, increase default timeout:
        # https://bugzilla.mozilla.org/show_bug.cgi?id=1007230#c802
        non_uv_pip_args = ["--timeout", str(c.get("pip_timeout", 120))]

        if c.get("find_links") and not c["pip_index"]:
            pip_args += ["--no-index"]

        non_uv_pip_args += ["--no-use-pep517"]

        # Add --find-links pages to look at. Add --trusted-host automatically if
        # the host isn't secure. This allows modern versions of pip to connect
        # without requiring an override.
        trusted_hosts = set()
        for link in c.get("find_links", []):
            parsed = urlparse.urlparse(link)

            try:
                socket.gethostbyname(parsed.hostname)
            except socket.gaierror as e:
                self.info("error resolving %s (ignoring): %s" % (parsed.hostname, e))
                continue

            pip_args += ["--find-links", link]
            if parsed.scheme != "https":
                trusted_hosts.add(parsed.hostname)

        for host in sorted(trusted_hosts):
            pip_args += ["--trusted-host", host]

        return pip_args, non_uv_pip_args

    @py3_venv_initialized
    def py3_install_requirement_files(
        self, requirements, pip_args=[], use_mozharness_pip_config=True
    ):
        """
        requirements - You can specify multiple requirements paths
        """
        pip_install_command_args = []
        pip_install_command_args += pip_args
        pip_install_non_uv_args = []

        if use_mozharness_pip_config:
            pip_args, pip_install_non_uv_args = self._mozharness_pip_args()
            pip_install_command_args += pip_args

        for requirement_path in requirements:
            pip_install_command_args += ["-r", requirement_path]

        pip_install_command = (
            pip_command(
                python_executable=self.py3_python_path,
                subcommand="install",
                args=pip_install_command_args,
                non_uv_args=pip_install_non_uv_args,
            ),
        )

        self.run_command(pip_install_command, env=self.query_env())


if __name__ == "__main__":
    """TODO: unit tests."""
    pass
