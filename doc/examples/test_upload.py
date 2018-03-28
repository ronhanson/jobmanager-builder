
import logging
import mongoengine
import subprocess
from jobmanager.common.job import Job


class ExecuteJob(Job):
    command = mongoengine.StringField(required=True)
    output = mongoengine.StringField(default=None)

    def process(self):
        self.log_info('ExecuteJob %s - Executing command...' % self.uuid)
        result = subprocess.run(self.command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.log_info(result.stdout)
        if result.stderr:
            self.log_error(result.stderr)
        result.check_returncode()
        self.output = result.stdout + " " + result.stderr