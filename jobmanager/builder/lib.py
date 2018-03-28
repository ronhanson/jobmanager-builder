#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu
""" 
(c) 2018 Ronan Delacroix
Python Job Manager Builder API
:author: Ronan Delacroix
"""
import os
import sys
import json
import shutil
import logging
import subprocess
import venv
import docker
import jinja2
from io import BytesIO
import tbx.process

BASE_IMAGE = "ronhanson/jobmanager-client:latest"

DOCKER_REGISTRY_URL = None
DOCKER_REGISTRY_USERNAME = None
DOCKER_REGISTRY_PASSWORD = None
#DOCKER_REGISTRY_EMAIL = None


def test_docker_api():
    """
    Dummy function to test Docker API connection.
    Might raise ConnectionErrors
    """
    client = docker.from_env()
    client.images.list()


class DockerBuilder:
    """
    Docker Builder class is used to create Job Manager Client docker images with jobs included alongside with their requirements.
    """
    def __init__(self, folder, image_name, tags, imports, requirements, apt_packages, base_image=None, logger=None, on_log_debug=None, on_log_progress=None):
        self.image_uuid = None
        self.image_id = None
        self.image_name = image_name
        self.tags = tags
        self.imports = imports
        self.requirements = requirements
        self.apt_packages = apt_packages
        # self.log = log_function  # callable
        self.jobs = []
        self.tasks = []
        self.logger = logger or logging.getLogger()
        self.on_log_progress = on_log_progress
        self.on_log_debug = on_log_debug
        self.image_url = None
        self.base_image = base_image or BASE_IMAGE
        self.registry_url = DOCKER_REGISTRY_URL
        self.dockerfile_content = None

        if self.on_log_debug:
            assert callable(self.on_log_debug)
        if self.on_log_progress:
            assert callable(self.on_log_progress)
        if not self.tags:
            self.tags = ['latest']

        self.package_root = folder
        self.validate(folder)

    def log_info(self, msg):
        if self.on_log_progress:
            self.on_log_progress(msg)
        self.logger.info(msg)

    def log_debug(self, msg):
        if self.on_log_debug:
            self.on_log_debug("\t" + msg)
        self.logger.debug(msg)

    def log_error(self, msg):
        if self.on_log_progress:
            self.on_log_progress(msg)
        self.logger.error(msg)

    def validate(self, folder):
        """
        Method called by constructor to
        :return: docker image object
        """
        venv_folder = None
        try:
            self.log_info("Starting validation.")
            self.package_root = self.find_package_root(folder)
            venv_folder = self.create_venv()
            self.test_import(venv_folder)
            self.log_info("Validation finished.")
        except Exception as e:
            self.log_error("Error : %s" % str(e))
            raise
        finally:
            if venv_folder:
                shutil.rmtree(venv_folder, ignore_errors=True)

    def build(self):
        """
        Main build method to create a docker image and push it to registry
        :return: docker image object
        """
        try:
            self.log_info("Starting build.")
            self.create_dockerfile()
            img = self.create_docker_image()
            if self.registry_url:
                self.push_docker_image(img)
            self.log_info("Build finished.")
            return img
        except Exception as e:
            self.log_error("Error : %s" % str(e))
            raise

    def find_package_root(self, folder):
        """
        Scan folder to get the package root containing all import modules.
        If no or only part of imported modules are found, raise exception.
        """
        self.log_info("Searching for package root folder to import %s" % ', '.join(self.imports))
        for root, dirs, files in os.walk(folder):
            found = 0
            for imp in self.imports:
                mod_path = imp.strip('./').replace('.', '/')
                if os.path.isfile(os.path.join(root, mod_path + ".py")) or os.path.isfile(
                        os.path.join(root, mod_path, "__init__.py")):
                    found += 1
            if found == 0:
                continue
            elif found != len(self.imports):
                raise Exception("Found %d imports in %s except we should have found %d" % (found, root, len(self.imports)))
            else:
                relpath = os.path.relpath(root, folder)
                self.log_info("Found package root in %s" % relpath)
                return root
        raise Exception("Found no entrypoint corresponding to '%s' in uploaded file." % (', '.join(self.imports)))

    def create_venv(self):
        """
        Create virtual env and add requirements.
        """
        self.log_info("Creating Virtual Env.")
        venv_folder = os.path.join(self.package_root, "venv")
        if not os.path.isdir(venv_folder):
            tmp_env = venv.EnvBuilder(system_site_packages=False, symlinks=False, with_pip=True)
            tmp_env.create(venv_folder)

            venv_pip = os.path.join(venv_folder, "bin/pip")

            self.log_info("Installing pip requirements in virtual env...")
            res = tbx.process.execute(
                "{pip} install jobmanager-common {requirements}".format(
                    pip=venv_pip,
                    requirements=' '.join(self.requirements)),
                logger=self.logger,
                line_function=self.log_debug,
                return_output=False
            )
            if res:
                raise Exception("Error while installing requirements %s : %s %s" % (
                    self.requirements, res.stdout.decode('utf-8'), res.stderr.decode('utf-8')))

        self.log_info("Virtual env OK. Requirements installed.")
        return venv_folder

    def test_import(self, venv_folder):
        """
        Test importing the imports/packages.
        """
        self.log_debug("Testing import of %s " % (','.join(self.imports)))
        package_tester_source = os.path.join(os.path.dirname(__file__), "package_tester.py")
        package_tester = os.path.join(self.package_root, "package_tester.py")
        shutil.copy(package_tester_source, package_tester)
        venv_python_executable = os.path.join(venv_folder, "bin/python")

        output = tbx.process.execute(
            "{python} {package_tester} {imports}".format(
                python=venv_python_executable,
                package_tester=package_tester,
                imports=" ".join(self.imports)
            ),
            logger=self.logger,
            env={'PYTHONPATH': self.package_root},
            return_output=True,
            timeout=10
        )

        result = json.loads(output)
        status = result.get('result')
        if status == "error" and result.get('error'):
            raise Exception("Error importing package %s :\n%s" % (','.join(self.imports), result.get('error')))

        assert result['result'] == "success"
        self.jobs = result.get('jobs', [])
        self.tasks = result.get('tasks', [])
        self.log_info(
            "Successful import %s - Job found : %s" % (','.join(self.imports), self.jobs))

        # clean
        os.remove(package_tester)
        shutil.rmtree(venv_folder, ignore_errors=True)

    def create_dockerfile(self):

        self.log_info("Building Dockerfile for %s" % self.image_name)

        build_script = os.path.join(self.package_root, 'build.sh')

        template = jinja2.Template("""FROM {{base_image}}
{% if apt_packages %}
RUN apt-get -y update && \
    apt-get -y --no-install-recommends install {{apt_packages}}  && \
    rm -rf /var/lib/apt/lists/*
{% endif %}
{% if requirements %}
RUN pip3 install --no-cache-dir {{requirements}}
{% endif %}
COPY . /opt/lib
{% if build_script_exists %}
RUN /opt/lib/build.sh
{% endif %}
ENV JOBMANAGER_CLIENT_IMPORTS="{{modules}}"
            """.strip(), trim_blocks=True, lstrip_blocks=True)
        dockerfile_content = template.render(
            apt_packages=' '.join(self.apt_packages),
            modules=','.join(self.imports),
            requirements=' '.join(self.requirements),
            build_script_exists=os.path.isfile(build_script),
            base_image=self.base_image
        )
        self.dockerfile_content = dockerfile_content
        return dockerfile_content

    def create_docker_image(self):
        """
        Create Dockerfile
        """
        registry_url = DOCKER_REGISTRY_URL or os.environ.get('DOCKER_REGISTRY_URL')
        registry_username = DOCKER_REGISTRY_USERNAME or os.environ.get('DOCKER_REGISTRY_USERNAME', None)
        registry_password = DOCKER_REGISTRY_PASSWORD or os.environ.get('DOCKER_REGISTRY_PASSWORD', None)

        dockerfile = BytesIO(self.dockerfile_content.encode('utf-8'))

        client = docker.from_env()

        if registry_url and registry_username:
            self.log_debug("login to registry %s@%s" % (registry_username, registry_url))
            client.login(registry=registry_url, username=registry_username, password=registry_password)  # email=email)
            self.log_info("Logged in to registry %s@%s" % (registry_username, registry_url))

        self.log_info("Building %s" % self.image_name)
        images = client.images.build(path=self.package_root, fileobj=dockerfile, tag=self.image_name)
        image = images[0]
        for t in self.tags:
            self.log_info("Adding tag %s to %s" % (t, self.image_name))
            image.tag(self.image_name, tag=t)
        self.log_info("Image %s - build success." % self.image_name)

        self.image_uuid = image.short_id[7:]
        self.image_id = str(image.id)[19:]

        image.reload()
        return image

    def push_docker_image(self, image):
        """
        Push docker image to repo
        """
        self.log_debug("Tagging image %s and uploading it to %s" % (self.image_name, self.registry_url))

        client = docker.from_env()

        registry_url = DOCKER_REGISTRY_URL or os.environ.get('DOCKER_REGISTRY_URL')
        registry_username = DOCKER_REGISTRY_USERNAME or os.environ.get('DOCKER_REGISTRY_USERNAME', None)
        registry_password = DOCKER_REGISTRY_PASSWORD or os.environ.get('DOCKER_REGISTRY_PASSWORD', None)

        def tag_repo(repo):
            for t in self.tags:
                self.log_info("Adding registry tag %s:%s" % (repo, t))
                image.tag(repo, t)

        registry_url = registry_url.rstrip('/')

        if registry_username:
            registry_username = registry_username.rstrip('/')
            self.log_debug("login to registry %s@%s" % (registry_username, registry_url))
            client.login(registry=registry_url, username=registry_username, password=registry_password)  # email=email)
            self.log_info("Logged in to registry %s@%s" % (registry_username, registry_url))

            repo_small_url = "%s/%s" % (registry_username, self.image_name)
            tag_repo(repo_small_url)

            repo_full_url = "%s/%s/%s" % (registry_url, registry_username, self.image_name)
            tag_repo(repo_full_url)
        else:
            repo_full_url = "%s/%s" % (registry_url, self.image_name)
            tag_repo(repo_full_url)

        for t in self.tags:
            self.log_info("Pushing image %s:%s ..." % (repo_full_url, t))
            client.images.push(repository=repo_full_url, tag=t)

        image.reload()
        self.image_url = [repo_full_url+":"+t for t in self.tags]
        return image
