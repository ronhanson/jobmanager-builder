#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu
""" 
(c) 2018 Ronan Delacroix
Python Job Manager Server API
:author: Ronan Delacroix
"""
from flask import Flask, request, Response, render_template, url_for, redirect, flash, jsonify
from werkzeug.utils import secure_filename
from functools import wraps
import os
import sys
import tbx
import tbx.text
import tbx.code
import logging
import tempfile
import traceback
import datetime
from functools import reduce
import operator
import shutil
from . import lib
import jobmanager.common.docker
from flask_socketio import SocketIO, send, emit, join_room, leave_room
import eventlet

eventlet.monkey_patch()


ARCHIVE_EXTENSIONS = reduce(operator.concat, [f[1] for f in shutil.get_unpack_formats()])

ALLOWED_EXTENSIONS = ['.py'] + ARCHIVE_EXTENSIONS

APP_NAME = "Job Manager"

# Flask
app = Flask("jobmanager-builder", static_folder='jobmanager/builder/static', static_url_path='/static', template_folder='jobmanager/builder/templates')
app.secret_key = "jobmanager-builder-secret-key-01"
app.jinja_env.lstrip_blocks = True
app.jinja_env.trim_blocks = True
log = logging.getLogger('werkzeug')
logging.getLogger('docker').setLevel(logging.INFO)
socketio = SocketIO(app)


@socketio.on('connect')
def on_connect():
    logging.info(request.sid + ' Connected to websocket')
    socketio.emit('progress message', {'message': request.sid + ' Connected to websocket'}, room=request.sid)

def serialize_response(result):
    mimetype = request.accept_mimetypes.best_match(tbx.text.mime_rendering_dict.keys(), default='application/json')
    if request.args.get('format') and request.args.get('format') in tbx.text.mime_shortcuts.keys():
        mimetype = tbx.text.mime_shortcuts.get(request.args.get('format'))
    code = 200

    return Response(tbx.text.render_dict_from_mimetype(result, mimetype), status=code, mimetype=mimetype)


# decorator
def serialize(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        return serialize_response(result)

    return wrapper


def save_uploaded_file(package_file, allowed_extension=ALLOWED_EXTENSIONS):
    package_folder = tempfile.mkdtemp()

    if not package_file or not package_file.filename or not os.path.splitext(package_file.filename)[1] in allowed_extension:
        raise Exception('No uploaded file or invalid one %s' % package_file)

    filename = secure_filename(package_file.filename)
    filepath = os.path.join(package_folder, filename)
    package_file.save(filepath)

    if os.path.splitext(filename)[1] in ARCHIVE_EXTENSIONS:
        package_folder = tempfile.mkdtemp()
        shutil.unpack_archive(filepath, package_folder)

    return package_folder, filename


@app.route('/')
def index():
    return render_template('index.html', title="%s - Docker image Builder" % APP_NAME, app_name=APP_NAME)


@app.route('/file')
def file():
    return render_template('file.html', title="%s - Docker image Builder" % APP_NAME, app_name=APP_NAME)


@app.route('/code')
def code():
    return render_template('code.html', title="%s - Docker image Builder" % APP_NAME, app_name=APP_NAME)


@app.route('/howto')
def howto():
    return render_template('howto.html', title="%s - Docker image Builder" % APP_NAME, app_name=APP_NAME)


@app.route('/list')
def listimage():
    # TODO: refresh tags and name (latest might not be latest anymore)
    image_list = jobmanager.common.docker.DockerImage.objects().to_safe_dict()
    return render_template('list.html', title="%s - Docker image Builder" % APP_NAME, image_list=image_list, app_name=APP_NAME)


@app.route('/build', methods=('POST',))
@serialize
def build():
    log.info("Build request received")
    if 'package' not in request.files:
        flash('No file part')
        return redirect(request.url)

    ws_sid = request.values.get('sid', '').strip()

    package_file = request.files.get('package')
    image_name = request.values.get('name').strip()
    imports = list(filter(None, request.values.get('imports', '').split(' ')))
    requirements = list(filter(None, request.values.get('pip', '').split(' ')))
    apt_packages = list(filter(None, request.values.get('apt', '').split(' ')))
    tags = list(filter(None, request.values.get('tags', '').split(' ')))
    full_log = []

    def on_log_debug(msg):
        full_log.append(msg)
        if ws_sid:
            socketio.emit('debug message', {'message': msg}, room=ws_sid)

    def on_log_progress(msg):
        full_log.append(msg)
        if ws_sid:
            socketio.emit('progress message', {'message': msg}, room=ws_sid)

    try:
        package_folder, filename = save_uploaded_file(package_file)

        log.info("File %s saved. Validating package, testing imports, requirements, etc..." % filename)

        docker_builder = lib.DockerBuilder(package_folder, image_name, tags, imports, requirements, apt_packages,
                                           logger=log, on_log_debug=on_log_debug, on_log_progress=on_log_progress)
        docker_image = docker_builder.build()

        log.info("Saving image to database...")
        img = DockerImage.objects(uuid=docker_builder.image_uuid).modify(
            upsert=True,
            new=True,
            image_id=docker_builder.image_id,
            name=docker_builder.image_name,
            url=docker_builder.image_url,
            tags=docker_image.tags,
            jobs=docker_builder.jobs,
            tasks=docker_builder.tasks,
            requirements=docker_builder.requirements,
            apt_packages=docker_builder.apt_packages,
            dockerfile=docker_builder.dockerfile_content,
            updated=datetime.datetime.utcnow()
        )

        log.info("Success! Image %s saved to database! ID=%s" % (image_name, img.uuid))

        # removing previously tagged images :
        log.info("Removing tags set to this image from other images.")
        DockerImage.objects(uuid__ne=img.uuid).update(pull_all__tags=docker_image.tags)
        DockerImage.objects(name__in=docker_image.tags, uuid__ne=img.uuid).update(name="")

        result = img.to_safe_dict()
        result.update({
            'file': filename,
            'result': "success",
            'message': "Success! Image build OK!",
            'details': '\n'.join(full_log)
        })
    except Exception as e:
        log.info("\nERROR %s\n" % str(e))
        result = {
            'result': "error",
            'message': str(e),
            'details': ('\n'.join(full_log)) + ''.join(traceback.format_exception(*sys.exc_info()))
        }
        log.exception("Error while building image...")
    finally:
        shutil.rmtree(package_folder, ignore_errors=True)

    return result


###
# Error handling
###
@app.errorhandler(Exception)
def unknown_error(e):
    logging.exception("Exception occured - " + str(e))
    mimetype = request.accept_mimetypes.best_match(tbx.text.mime_rendering_dict.keys(), default='application/json')
    result = {
        'status': 'ERROR',
        'code': 500,
        'type': e.__class__.__name__,
        'message': str(e),
        'url': request.path,
        'data': request.data.decode('UTF-8'),
        'values': request.values
    }
    return Response(tbx.text.render_dict_from_mimetype(result, mimetype), status=500, mimetype=mimetype)


@app.errorhandler(404)
def page_not_found(e):
    mimetype = request.accept_mimetypes.best_match(tbx.text.mime_rendering_dict.keys(), default='application/json')
    result = {
        'status': 'ERROR',
        'code': 404,
        'type': '404 Not Found',
        'message': 'Url is unknown',
        'url': request.path,
        'data': request.data.decode('UTF-8'),
        'values': request.values
    }
    return Response(tbx.text.render_dict_from_mimetype(result, mimetype), status=404, mimetype=mimetype)


###
# Run
###
def run_api(host='0.0.0.0', port=5001, debug=False):

    app.add_url_rule('/favicon.ico', endpoint='favicon', redirect_to='/static/favicon.ico')

    socketio.run(app, host=host, port=port, debug=debug)
    logging.info('Flask App exited gracefully, exiting...')

