
import mongoengine
import subprocess
from jobmanager.common.job import Job


def make_job(job_name, **kwargs):
    """
    Decorator to create a Job from a function.
    Give a job name and add extra fields to the job.

        @make_job("ExecuteDecJob",
                  command=mongoengine.StringField(required=True),
                  output=mongoengine.StringField(default=None))
        def execute(job: Job):
            job.log_info('ExecuteJob %s - Executing command...' % job.uuid)
            result = subprocess.run(job.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            job.output = result.stdout.decode('utf-8') + " " + result.stderr.decode('utf-8')

    """
    def wraps(func):
        kwargs['process'] = func
        job = type(job_name, (Job,), kwargs)
        globals()[job_name] = job
        return job
    return wraps


@make_job("ExecuteDecJob",
          command=mongoengine.StringField(required=True),
          output=mongoengine.StringField(default=None))
def execute(job: Job):
    job.log_info('ExecuteJob %s - Executing command...' % job.uuid)
    result = subprocess.run(job.command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    job.log_info(result.stdout)
    if result.stderr:
        job.log_error(result.stderr)
    result.check_returncode()
    job.output = result.stdout.decode('utf-8') + " " + result.stderr.decode('utf-8')

import pdb
pdb.set_trace()