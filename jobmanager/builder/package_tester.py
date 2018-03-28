#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu
""" 
(c) 2018 Ronan Delacroix
Python Job Manager Docker Builder - Package Tester / Import checker
:author: Ronan Delacroix
"""
import sys
import re
import json
from jobmanager.common.job import Job, JobTask


def get_subclasses(klass):
    assert isinstance(klass, type)
    klasses = klass.__subclasses__()
    klasses2 = klasses
    for y in klasses:
        klasses2 += get_subclasses(y)
    return list(set(klasses2))


def load_module(name):
    """
    Load module in the format 'json.tool'
    """
    mod = __import__(name)
    for sub in name.split('.')[1:]:
        mod = getattr(mod, sub)
    return mod


def parse_handler(handler):
    """
    Parse handler to retrieve module name and function name.
    """
    match = re.match('^([\w|-]+(\.[\w|-]+)*)$', handler)
    if not match:
        raise ValueError('malformed handler - {!r}'.format(handler))

    mod_name = match.group(1)
    return mod_name


def load_handler(handler):
    """
    Load handler function from handler.
    handler is in the format 'module.sub:handler_name'
    """
    mod_name = parse_handler(handler)
    load_module(mod_name)
    return


def main(handlers):
    try:
        for handler in handlers:
            load_module(handler)
        all_job_sub_classes = [str(c.__name__) for c in get_subclasses(Job)]
        all_task_sub_classes = [str(c.__name__) for c in get_subclasses(JobTask)]
        print(json.dumps({
            "result": "success",
            "handlers": handlers,
            "jobs": all_job_sub_classes,
            "job_tasks": all_task_sub_classes,
            "details": "Handlers %s loaded OK - found jobs types : %s" % ('/'.join(handlers), ', '.join(all_job_sub_classes))
        }, indent=True))
        return 0
    except Exception as e:
        print(json.dumps({
            "result": "error",
            "handlers": handlers,
            "error": str(e),
            "details": "ERROR while loading handler %s" % ('/'.join(handlers))
        }, indent=True))
        return 1


if __name__ == "__main__":
    res = main(sys.argv[1:])
    sys.exit(res)
