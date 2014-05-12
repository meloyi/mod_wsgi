from __future__ import print_function, division

import os
import sys
import shutil
import subprocess
import optparse
import math
import signal
import threading
import atexit
import imp
import pwd
import grp

try:
    import Queue as queue
except ImportError:
    import queue

from . import apxs_config

_py_version = '%s%s' % sys.version_info[:2]
_py_soabi = ''
_py_soext = '.so'

try:
    import imp
    import sysconfig

    _py_soabi = sysconfig.get_config_var('SOABI')
    _py_soext = sysconfig.get_config_var('SO')

except ImportError:
    pass

MOD_WSGI_SO = 'mod_wsgi-py%s%s' % (_py_version, _py_soext)
MOD_WSGI_SO = os.path.join(os.path.dirname(__file__), MOD_WSGI_SO)

if not os.path.exists(MOD_WSGI_SO) and _py_soabi:
    MOD_WSGI_SO = 'mod_wsgi-py%s.%s%s' % (_py_version, _py_soabi, _py_soext)
    MOD_WSGI_SO = os.path.join(os.path.dirname(__file__), MOD_WSGI_SO)

def where():
    return MOD_WSGI_SO

def default_run_user():
   return pwd.getpwuid(os.getuid()).pw_name

def default_run_group():
   return grp.getgrgid(pwd.getpwuid(os.getuid()).pw_gid).gr_name

def find_program(names, default=None, paths=[]):
    for name in names:
        for path in os.environ['PATH'].split(':') + paths:
            program = os.path.join(path, name)
            if os.path.exists(program):
                return program
    return default

def find_mimetypes():
    import mimetypes
    for name in mimetypes.knownfiles:
        if os.path.exists(name):
            return name
            break
    else:
        return name

APACHE_GENERAL_CONFIG = """
LoadModule version_module '%(modules_directory)s/mod_version.so'

ServerName %(host)s
ServerRoot '%(server_root)s'
PidFile '%(pid_file)s'

<IfVersion >= 2.4>
DefaultRuntimeDir '%(server_root)s'
</IfVersion>

ServerSignature Off

User ${WSGI_RUN_USER}
Group ${WSGI_RUN_GROUP}

<IfDefine WSGI_LISTENER_HOST>
Listen %(host)s:%(port)s
</IfDefine>
<IfDefine !WSGI_LISTENER_HOST>
Listen %(port)s
</IfDefine>

<IfVersion < 2.4>
LockFile '%(server_root)s/accept.lock'
</IfVersion>

<IfVersion >= 2.4>
<IfModule !mpm_event_module>
<IfModule !mpm_worker_module>
<IfModule !mpm_prefork_module>
<IfDefine WSGI_MPM_EVENT_MODULE>
LoadModule mpm_event_module '%(modules_directory)s/mod_mpm_event.so'
</IfDefine>
<IfDefine WSGI_MPM_WORKER_MODULE>
LoadModule mpm_worker_module '%(modules_directory)s/mod_mpm_worker.so'
</IfDefine>
<IfDefine WSGI_MPM_PREFORK_MODULE>
LoadModule mpm_prefork_module '%(modules_directory)s/mod_mpm_prefork.so'
</IfDefine>
</IfModule>
</IfModule>
</IfModule>
</IfVersion>

<IfVersion >= 2.4>
LoadModule access_compat_module '%(modules_directory)s/mod_access_compat.so'
LoadModule unixd_module '%(modules_directory)s/mod_unixd.so'
LoadModule authn_core_module '%(modules_directory)s/mod_authn_core.so'
LoadModule authz_core_module '%(modules_directory)s/mod_authz_core.so'
</IfVersion>

LoadModule authz_host_module '%(modules_directory)s/mod_authz_host.so'
LoadModule mime_module '%(modules_directory)s/mod_mime.so'
LoadModule rewrite_module '%(modules_directory)s/mod_rewrite.so'
LoadModule alias_module '%(modules_directory)s/mod_alias.so'
LoadModule dir_module '%(modules_directory)s/mod_dir.so'
LoadModule wsgi_module '%(mod_wsgi_so)s'

<IfDefine WSGI_SERVER_STATUS>
LoadModule status_module '%(modules_directory)s/mod_status.so'
</IfDefine>

<IfVersion < 2.4>
DefaultType text/plain
</IfVersion>

TypesConfig '%(mime_types)s'

HostnameLookups Off
MaxMemFree 64
Timeout 60

LimitRequestBody %(limit_request_body)s

<Directory />
    AllowOverride None
    Order deny,allow
    Deny from all
</Directory>

WSGIPythonHome '%(python_home)s'
WSGIRestrictEmbedded On
WSGISocketPrefix %(server_root)s/wsgi
<IfDefine WSGI_MULTIPROCESS>
WSGIDaemonProcess %(host)s:%(port)s display-name='%(process_name)s' \\
   home='%(working_directory)s' processes=%(processes)s threads=%(threads)s \\
   maximum-requests=%(maximum_requests)s python-eggs='%(python_eggs)s' \\
   lang='%(lang)s' locale='%(locale)s'
</IfDefine>
<IfDefine !WSGI_MULTIPROCESS>
WSGIDaemonProcess %(host)s:%(port)s display-name='%(process_name)s' \\
   home='%(working_directory)s' threads=%(threads)s \\
   maximum-requests=%(maximum_requests)s python-eggs='%(python_eggs)s' \\
   lang='%(lang)s' locale='%(locale)s'
</IfDefine>
WSGICallableObject '%(callable_object)s'
WSGIPassAuthorization On

<IfDefine WSGI_SERVER_STATUS>
ExtendedStatus On
<Location /server-status>
    SetHandler server-status
    Order deny,allow
    Deny from all
    Allow from localhost
</Location>
</IfDefine>

<IfDefine WSGI_KEEP_ALIVE>
KeepAlive On
KeepAliveTimeout %(keep_alive_timeout)s
</IfDefine>
<IfDefine !WSGI_KEEP_ALIVE>
KeepAlive Off
</IfDefine>

ErrorLog '%(error_log)s'
LogLevel %(log_level)s

<IfDefine WSGI_ACCESS_LOG>
LoadModule log_config_module %(modules_directory)s/mod_log_config.so
LogFormat "%%h %%l %%u %%t \\"%%r\\" %%>s %%b" common
CustomLog "%(log_directory)s/access_log" common
</IfDefine>

<IfModule mpm_prefork_module>
ServerLimit %(prefork_server_limit)s
StartServers %(prefork_start_servers)s
MaxClients %(prefork_max_clients)s
MinSpareServers %(prefork_min_spare_servers)s
MaxSpareServers %(prefork_max_spare_servers)s
MaxRequestsPerChild 0
</IfModule>

<IfModule mpm_worker_module>
ServerLimit %(worker_server_limit)s
ThreadLimit %(worker_thread_limit)s
StartServers %(worker_start_servers)s
MaxClients %(worker_max_clients)s
MinSpareThreads %(worker_min_spare_threads)s
MaxSpareThreads %(worker_max_spare_threads)s
ThreadsPerChild %(worker_threads_per_child)s
MaxRequestsPerChild 0
ThreadStackSize 262144
</IfModule>

<IfModule mpm_event_module>
ServerLimit %(worker_server_limit)s
ThreadLimit %(worker_thread_limit)s
StartServers %(worker_start_servers)s
MaxClients %(worker_max_clients)s
MinSpareThreads %(worker_min_spare_threads)s
MaxSpareThreads %(worker_max_spare_threads)s
ThreadsPerChild %(worker_threads_per_child)s
MaxRequestsPerChild 0
ThreadStackSize 262144
</IfModule>

DocumentRoot '%(document_root)s'

<Directory '%(server_root)s'>
<Files handler.wsgi>
    Order allow,deny
    Allow from all
</Files>
</Directory>

<Directory '%(document_root)s'>
    RewriteEngine On
    RewriteCond %%{REQUEST_FILENAME} !-f
<IfDefine WSGI_SERVER_STATUS>
    RewriteCond %%{REQUEST_URI} !/server-status
</IfDefine>
    RewriteRule .* - [H=wsgi-handler]
    Order allow,deny
    Allow from all
</Directory>

WSGIHandlerScript wsgi-handler '%(server_root)s/handler.wsgi' \\
    process-group='%(host)s:%(port)s' application-group=%%{GLOBAL}
WSGIImportScript '%(server_root)s/handler.wsgi' \\
    process-group='%(host)s:%(port)s' application-group=%%{GLOBAL}
"""

APACHE_ALIAS_DIRECTORY_CONFIG = """
Alias '%(mount_point)s' '%(directory)s'

<Directory '%(directory)s'>
    Order allow,deny
    Allow from all
</Directory>
"""

APACHE_ALIAS_FILENAME_CONFIG = """
Alias '%(mount_point)s' '%(directory)s/%(filename)s'

<Directory '%(directory)s'>
<Files '%(filename)s'>
    Order allow,deny
    Allow from all
</Files>
</Directory>
"""

APACHE_ALIAS_DOCUMENTATION = """
Alias /__wsgi__/docs '%(documentation_directory)s'
Alias /__wsgi__/images '%(images_directory)s'

<Directory '%(documentation_directory)s'>
    DirectoryIndex index.html
    Order allow,deny
    Allow from all
</Directory>

<Directory '%(images_directory)s'>
    Order allow,deny
    Allow from all
</Directory>
"""

APACHE_ERROR_DOCUMENT_CONFIG = """
ErrorDocument '%(status)s' '%(document)s'
"""

APACHE_INCLUDE_CONFIG = """
Include '%(filename)s'
"""

APACHE_WDB_CONFIG = """
WSGIDaemonProcess wdb-server display-name=%%{GROUP} threads=1
WSGIImportScript '%(server_root)s/wdb-server.py' \\
    process-group=wdb-server application-group=%%{GLOBAL}
"""

def generate_apache_config(options):
    with open(options['httpd_conf'], 'w') as fp:
        print(APACHE_GENERAL_CONFIG % options, file=fp)

        if options['url_aliases']:
            for mount_point, target in sorted(options['url_aliases'],
                    reverse=True):
                target = os.path.abspath(target)

                if os.path.isdir(target):
                    directory = target

                    print(APACHE_ALIAS_DIRECTORY_CONFIG % dict(
                            mount_point=mount_point, directory=directory),
                            file=fp)

                else:
                    directory = os.path.dirname(target)
                    filename = os.path.basename(target)

                    print(APACHE_ALIAS_FILENAME_CONFIG % dict(
                            mount_point=mount_point, directory=directory,
                            filename=filename), file=fp)

        print(APACHE_ALIAS_DOCUMENTATION % options, file=fp)

        if options['error_documents']:
            for status, document in options['error_documents']:
                print(APACHE_ERROR_DOCUMENT_CONFIG % dict(status=status,
                        document=document.replace("'", "\\'")), file=fp)

        if options['include_files']:
            for filename in options['include_files']:
                filename = os.path.abspath(filename)
                print(APACHE_INCLUDE_CONFIG % dict(filename=filename),
                        file=fp)

        if options['with_wdb']:
            print(APACHE_WDB_CONFIG % options, file=fp)

_interval = 1.0
_times = {}
_files = []

_running = False
_queue = queue.Queue()
_lock = threading.Lock()

def _restart(path):
    _queue.put(True)
    prefix = 'monitor (pid=%d):' % os.getpid()
    print('%s Change detected to "%s".' % (prefix, path), file=sys.stderr)
    print('%s Triggering process restart.' % prefix, file=sys.stderr)
    os.kill(os.getpid(), signal.SIGINT)

def _modified(path):
    try:
        # If path doesn't denote a file and were previously
        # tracking it, then it has been removed or the file type
        # has changed so force a restart. If not previously
        # tracking the file then we can ignore it as probably
        # pseudo reference such as when file extracted from a
        # collection of modules contained in a zip file.

        if not os.path.isfile(path):
            return path in _times

        # Check for when file last modified.

        mtime = os.stat(path).st_mtime
        if path not in _times:
            _times[path] = mtime

        # Force restart when modification time has changed, even
        # if time now older, as that could indicate older file
        # has been restored.

        if mtime != _times[path]:
            return True
    except:
        # If any exception occured, likely that file has been
        # been removed just before stat(), so force a restart.

        return True

    return False

def _monitor():
    global _files

    while 1:
        # Check modification times on all files in sys.modules.

        for module in list(sys.modules.values()):
            if not hasattr(module, '__file__'):
                continue
            path = getattr(module, '__file__')
            if not path:
                continue
            if os.path.splitext(path)[1] in ['.pyc', '.pyo', '.pyd']:
                path = path[:-1]
            if _modified(path):
                return _restart(path)

        # Check modification times on files which have
        # specifically been registered for monitoring.

        for path in _files:
            if _modified(path):
                return _restart(path)

        # Go to sleep for specified interval.

        try:
            return _queue.get(timeout=_interval)
        except:
            pass

_thread = threading.Thread(target=_monitor)
_thread.setDaemon(True)

def _exiting():
    try:
        _queue.put(True)
    except:
        pass
    _thread.join()

def track_changes(path):
    if not path in _files:
        _files.append(path)

def start_reloader(interval=1.0):
    global _interval
    if interval < _interval:
        _interval = interval

    global _running
    _lock.acquire()
    if not _running:
        prefix = 'monitor (pid=%d):' % os.getpid()
        print('%s Starting change monitor.' % prefix, file=sys.stderr)
        _running = True
        _thread.start()
        atexit.register(_exiting)
    _lock.release()

class ApplicationHandler(object):

    def __init__(self, script, callable_object='application',
            with_newrelic=False, with_wdb=False):
        self.script = script
        self.callable_object = callable_object

        self.module = imp.new_module('__wsgi__')
        self.module.__file__ = script

        with open(script, 'r') as fp:
            code = compile(fp.read(), script, 'exec', dont_inherit=True)
            exec(code, self.module.__dict__)

        self.application = getattr(self.module, callable_object)

        sys.modules['__wsgi__'] = self.module

        try:
            self.mtime = os.path.getmtime(script)
        except:
            self.mtime = None

        if with_newrelic:
            self.setup_newrelic()

        if with_wdb:
            self.setup_wdb()

    def setup_newrelic(self):
        import newrelic.agent

        config_file = os.environ.get('NEW_RELIC_CONFIG_FILE')
        environment = os.environ.get('NEW_RELIC_ENVIRONMENT')

        global_settings = newrelic.agent.global_settings()
        if global_settings.log_file is None:
            global_settings.log_file = 'stderr'

        newrelic.agent.initialize(config_file, environment)
        newrelic.agent.register_application()

        self.application = newrelic.agent.WSGIApplicationWrapper(
                self.application)

    def setup_wdb(self):
        from wdb.ext import WdbMiddleware
        self.application = WdbMiddleware(self.application)

    def reload_required(self, environ):
        try:
            mtime = os.path.getmtime(self.script)
        except:
            mtime = None

        return mtime != self.mtime

    def handle_request(self, environ, start_response):
        # Strip out the leading component due to internal redirect in
        # Apache when using web application as fallback resource.

        script_name = environ.get('SCRIPT_NAME')
        path_info = environ.get('PATH_INFO')

        environ['SCRIPT_NAME'] = ''
        environ['PATH_INFO'] = script_name + path_info

        return self.application(environ, start_response)

    def __call__(self, environ, start_response):
        return self.handle_request(environ, start_response)

WSGI_HANDLER_SCRIPT = """
import mod_wsgi.server

script = '%(script)s'
callable_object = '%(callable_object)s'
with_newrelic = %(with_newrelic)s
with_wdb = %(with_wdb)s

handler = mod_wsgi.server.ApplicationHandler(script, callable_object,
        with_newrelic=with_newrelic, with_wdb=with_wdb)

reload_required = handler.reload_required
handle_request = handler.handle_request

if %(reload_on_changes)s:
    mod_wsgi.server.start_reloader()
"""

WSGI_DEFAULT_SCRIPT = """
CONTENT = b'''
<html>
<head>
<title>My web site runs on Malt Whiskey</title>
</head>
<body style="margin-top: 100px;">
<table align="center"; style="width: 850px;" border="0" cellpadding="30">
<tbody>
<tr>
<td>
<img style="width: 275px; height: 445px;"
  src="/__wsgi__/images/snake-whiskey.jpg">
</td>
<td style="text-align: center;">
<span style="font-family: Arial,Helvetica,sans-serif;
  font-weight: bold; font-size: 70px;">
My web site<br>runs on<br>Malt Whiskey<br>
<br>
</span>
<span style="font-family: Arial,Helvetica,sans-serif;
  font-weight: bold;">
For further information on configuring mod_wsgi,<br>
see the <a href="%(documentation_url)s">documentation</a>.
</span>
</td>
</tr>
</tbody>
</table>
</body>
</html>
'''

def application(environ, start_response):
    status = '200 OK'
    output = CONTENT

    response_headers = [('Content-type', 'text/html'),
                        ('Content-Length', str(len(output)))]
    start_response(status, response_headers)

    return [output]
"""

def generate_wsgi_handler_script(options):
    path = os.path.join(options['server_root'], 'handler.wsgi')
    with open(path, 'w') as fp:
        print(WSGI_HANDLER_SCRIPT % options, file=fp)

    path = os.path.join(options['server_root'], 'default.wsgi')
    with open(path, 'w') as fp:
        print(WSGI_DEFAULT_SCRIPT % options, file=fp)

WDB_SERVER_SCRIPT = """
from wdb_server import server
try:
    from wdb_server.sockets import handle_connection
except ImportError:
    from wdb_server.streams import handle_connection

from tornado.ioloop import IOLoop
from tornado.options import options
from tornado.netutil import bind_sockets, add_accept_handler
from threading import Thread

def run_server():
    ioloop = IOLoop.instance()
    sockets = bind_sockets(options.socket_port)
    for socket in sockets:
        add_accept_handler(socket, handle_connection, ioloop)
    server.listen(options.server_port)
    ioloop.start()

thread = Thread(target=run_server)
thread.setDaemon(True)
thread.start()
"""

def generate_wdb_server_script(options):
    path = os.path.join(options['server_root'], 'wdb-server.py')
    with open(path, 'w') as fp:
        print(WDB_SERVER_SCRIPT, file=fp)

WSGI_CONTROL_SCRIPT = """
#!/bin/sh

HTTPD="%(httpd_executable)s %(httpd_arguments)s"

WSGI_RUN_USER="${WSGI_RUN_USER:-%(user)s}"
WSGI_RUN_GROUP="${WSGI_RUN_GROUP:-%(group)s}"

export WSGI_RUN_USER
export WSGI_RUN_GROUP

ACMD="$1"
ARGV="$@"

if test -f %(server_root)s/envvars; then
    . %(server_root)s/envvars
fi

STATUSURL="http://%(host)s:%(port)s/server-status"

if [ "x$ARGV" = "x" ] ; then
    ARGV="-h"
fi

case $ACMD in
start|stop|restart|graceful|graceful-stop)
    exec $HTTPD -k $ARGV
    ;;
configtest)
    exec $HTTPD -t
    ;;
status)
    exec %(python_executable)s -m webbrowser -t $STATUSURL
    ;;
*)
    exec $HTTPD $ARGV
esac
"""

APACHE_ENVVARS_FILE = """
. %(envvars_script)s
"""

def generate_control_scripts(options):
    path = os.path.join(options['server_root'], 'server-admin')
    with open(path, 'w') as fp:
        print(WSGI_CONTROL_SCRIPT.lstrip() % options, file=fp)

    os.chmod(path, 0o755)

    path = os.path.join(options['server_root'], 'envvars')
    with open(path, 'w') as fp:
        if options['envvars_script']:
            print(APACHE_ENVVARS_FILE.lstrip() % options, file=fp)

option_list = (
    optparse.make_option('--host', default=None, metavar='IP-ADDRESS',
            help='The specific host (IP address) interface on which '
            'requests are to be accepted. Defaults to listening on '
            'all host interfaces.'),
    optparse.make_option('--port', default=8000, type='int',
            metavar='NUMBER', help='The specific port to bind to and '
            'on which requests are to be accepted. Defaults to port 8000.'),

    optparse.make_option('--processes', type='int', metavar='NUMBER',
            help='The number of worker processes (instances of the WSGI '
            'application) to be started up and which will handle requests '
            'concurrently. Defaults to a single process.'),
    optparse.make_option('--threads', type='int', default=5, metavar='NUMBER',
            help='The number of threads in the request thread pool of '
            'each process for handling requests. Defaults to 5 in each '
            'process.'),

    optparse.make_option('--max-clients', type='int', default=None,
            metavar='NUMBER', help='The maximum number of simultaneous '
            'client connections that will be accepted. This will default '
            'to being 1.25 times the total number of threads in the '
            'request thread pools across all process handling requests.'),

    optparse.make_option('--callable-object', default='application',
            metavar='NAME', help='The name of the entry point for the WSGI '
            'application within the WSGI script file. Defaults to '
            'the name \'application\'.'),

    optparse.make_option('--limit-request-body', type='int', default=10485760,
            metavar='NUMBER', help='The maximum number of bytes which are '
            'allowed in a request body. Defaults to 10485760 (10MB).'),
    optparse.make_option('--maximum-requests', type='int', default=0,
            metavar='NUMBER', help='The number of requests after which '
            'any one worker process will be restarted and the WSGI '
            'application reloaded. Defaults to 0, indicating that the '
            'worker process should never be restarted based on the number '
            'of requests received.'),
    optparse.make_option('--reload-on-changes', action='store_true',
            default=False, help='Flag indicating whether worker processes '
            'should be automatically restarted when any Python code file '
            'loaded by the WSGI application has been modified. Defaults to '
            'being disabled. When reloading on any code changes is disabled, '
            'the worker processes will still though be reloaded if the '
            'WSGI script file itself is modified.'),

    optparse.make_option('--user', default=default_run_user(), metavar='NAME',
            help='When being run by the root user, the user that the WSGI '
            'application should be run as.'),
    optparse.make_option('--group', default=default_run_group(),
            metavar='NAME', help='When being run by the root user, the group '
            'that the WSGI application should be run as.'),

    optparse.make_option('--document-root', metavar='DIRECTORY-PATH',
            help='The directory which should be used as the document root '
            'and which contains any static files.'),

    optparse.make_option('--url-alias', action='append', nargs=2,
            dest='url_aliases', metavar='URL-PATH FILE-PATH|DIRECTORY-PATH',
            help='Map a single static file or a directory of static files '
            'to a sub URL.'),
    optparse.make_option('--error-document', action='append', nargs=2,
            dest='error_documents', metavar='STATUS URL-PATH', help='Map '
            'a specific sub URL as the handler for HTTP errors generated '
            'by the web server.'),

    optparse.make_option('--keep-alive-timeout', type='int', default=0,
            metavar='SECONDS', help='The number of seconds which a client '
            'connection will be kept alive to allow subsequent requests '
            'to be made over the same connection. Defaults to 0, indicating '
            'that keep alive connections are disabled.'),

    optparse.make_option('--server-status', action='store_true',
            default=False, help='Flag indicating whether web server status '
            'will be available at the /server-status sub URL. Defaults to '
            'being disabled'),
    optparse.make_option('--include-file', action='append',
            dest='include_files', metavar='FILE-PATH', help='Specify the '
            'path to an additional web server configuration file to be '
            'included at the end of the generated web server configuration '
            'file.'),

    optparse.make_option('--envvars-script', metavar='FILE-PATH',
            help='Specify an alternate script file for user defined web '
            'server environment variables. Defaults to using the '
            '\'envvars\' stored under the server root directory.'),
    optparse.make_option('--lang', default='en_US.UTF-8', metavar='NAME',
            help='Specify the default language locale as normally defined '
            'by the LANG environment variable. Defaults to \'en_US.UTF-8\'.'),
    optparse.make_option('--locale', default='en_US.UTF-8', metavar='NAME',
            help='Specify the default natural language formatting style '
            'as normally defined by the LC_ALL environment variable. '
            'Defaults to \'en_US.UTF-8\'.'),

    optparse.make_option('--working-directory', metavar='DIRECTORY-PATH',
            help='Specify the directory which should be used as the '
            'current working directory of the WSGI application. This '
            'directory will be searched when importing Python modules '
            'so long as the WSGI application doesn\'t subsequently '
            'change the current working directory. Defaults to the '
            'directory this script is run from.'),

    optparse.make_option('--pid-file', metavar='FILE-PATH',
            help='Specify an alternate file to be used to store the '
            'process ID for the root process of the web server.'),

    optparse.make_option('--server-root', metavar='DIRECTORY-PATH',
            help='Specify an alternate directory for where the generated '
            'web server configuration, startup files and logs will be '
            'stored. Defaults to a sub directory of /tmp.'),
    optparse.make_option('--log-directory', metavar='DIRECTORY-PATH',
            help='Specify an alternate directory for where the log files '
            'will be stored. Defaults to the server root directory.'),
    optparse.make_option('--log-level', default='info', metavar='NAME',
            help='Specify the log level for logging. Defaults to \'info\'.'),
    optparse.make_option('--access-log', action='store_true', default=False,
            help='Flag indicating whether the web server access log '
            'should be enabled. Defaults to being disabled.'),
    optparse.make_option('--startup-log', action='store_true', default=False,
            help='Flag indicating whether the web server startup log should '
            'be enabled. Defaults to being disabled.'),

    optparse.make_option('--python-eggs', metavar='DIRECTORY-PATH',
            help='Specify an alternate directory which should be used for '
            'unpacking of Python eggs. Defaults to a sub directory of '
            'the server root directory.'),

    optparse.make_option('--httpd-executable', default=apxs_config.HTTPD,
            metavar='FILE-PATH', help='Override the path to the Apache web '
            'server executable.'),
    optparse.make_option('--modules-directory', default=apxs_config.LIBEXECDIR,
            metavar='DIRECTORY-PATH', help='Override the path to the Apache '
            'web server modules directory.'),
    optparse.make_option('--mime-types', default=find_mimetypes(),
            metavar='FILE-PATH', help='Override the path to the mime types '
            'file used by the web server.'),

    optparse.make_option('--with-newrelic', action='store_true',
            default=False, help='Flag indicating whether New Relic '
            'performance monitoring should be enabled for the WSGI '
            'application.'),
    optparse.make_option('--with-wdb', action='store_true', default=False,
            help='Flag indicating whether the wdb interactive debugger '
            'should be enabled for the WSGI application.'),

    optparse.make_option('--enable-docs', action='store_true', default=False,
            help='Flag indicating whether the mod_wsgi documentation should '
            'be made available at the /__wsgi__/docs sub URL.'),
)

def cmd_setup_server(params, usage=None):
    formatter = optparse.IndentedHelpFormatter()
    formatter.set_long_opt_delimiter(' ')

    usage = usage or '%prog setup-server script [options]'
    parser = optparse.OptionParser(usage=usage, option_list=option_list,
            formatter=formatter)

    (options, args) = parser.parse_args(params)

    return _cmd_setup_server(args, vars(options))

def _mpm_module_defines(modules_directory):
    result = []
    workers = ['event', 'worker', 'prefork']
    for name in workers:
        if os.path.exists(os.path.join(modules_directory,
                'mod_mpm_%s.so' % name)):
            result.append('-DWSGI_MPM_%s_MODULE' % name.upper())
    return result

def _cmd_setup_server(args, options):
    options['mod_wsgi_so'] = where()

    options['working_directory'] = options['working_directory'] or os.getcwd()

    if not options['host']:
        options['listener_host'] = None
        options['host'] = 'localhost'
    else:
        options['listener_host'] = options['host']

    options['process_name'] = '(wsgi:%s:%s:%s)' % (options['host'],
            options['port'], os.getuid())

    if not options['server_root']:
        options['server_root'] = '/tmp/mod_wsgi-%s:%s:%s' % (options['host'],
                options['port'], os.getuid())

    try:
        os.mkdir(options['server_root'])
    except Exception:
        pass

    if not args:
        options['script'] = os.path.join(options['server_root'],
                'default.wsgi')
        options['enable_docs'] = True
    else:
        options['script'] = os.path.abspath(args[0])

    options['documentation_directory'] = os.path.join(os.path.dirname(
            os.path.dirname(__file__)), 'docs')
    options['images_directory'] = os.path.join(os.path.dirname(
            os.path.dirname(__file__)), 'images')

    if os.path.exists(os.path.join(options['documentation_directory'],
            'index.html')):
        options['documentation_url'] = '/__wsgi__/docs/'
    else:
        options['documentation_url'] = 'http://www.modwsgi.org/'

    options['script_directory'] = os.path.dirname(options['script'])
    options['script_filename'] = os.path.basename(options['script'])

    if not os.path.isabs(options['server_root']):
        options['server_root'] = os.path.abspath(options['server_root'])

    if not options['document_root']:
        options['document_root'] = os.path.join(options['server_root'],
                'htdocs')

    try:
        os.mkdir(options['document_root'])
    except Exception:
        pass

    if not os.path.isabs(options['document_root']):
        options['document_root'] = os.path.abspath(options['document_root'])

    if not options['log_directory']:
        options['log_directory'] = options['server_root']

    try:
        os.mkdir(options['log_directory'])
    except Exception:
        pass

    if not os.path.isabs(options['log_directory']):
        options['log_directory'] = os.path.abspath(options['log_directory'])

    options['error_log'] = os.path.join(options['log_directory'], 'error_log')

    options['pid_file'] = ((options['pid_file'] and os.path.abspath(
            options['pid_file'])) or os.path.join(options['server_root'],
            'httpd.pid'))

    options['python_eggs'] = (os.path.abspath(options['python_eggs']) if
            options['python_eggs'] is not None else None)

    if options['python_eggs'] is None:
        options['python_eggs'] = os.path.join(options['server_root'],
                'python-eggs')

    try:
        os.mkdir(options['python_eggs'])
    except Exception:
        pass

    options['multiprocess'] = options['processes'] is not None
    options['processes'] = options['processes'] or 1

    options['python_home'] = sys.prefix

    options['keep_alive'] = options['keep_alive_timeout'] != 0

    generate_wsgi_handler_script(options)

    if options['with_wdb']:
        generate_wdb_server_script(options)

    max_clients = options['processes'] * options['threads']

    if options['max_clients'] is not None:
        max_clients = max(options['max_clients'], max_clients)
    else:
        max_clients = int(1.25 * max_clients)

    options['prefork_max_clients'] = max_clients
    options['prefork_server_limit'] = max_clients
    options['prefork_start_servers'] = max(1, int(0.1 * max_clients))
    options['prefork_min_spare_servers'] = options['prefork_start_servers']
    options['prefork_max_spare_servers'] = max(1, int(0.4 * max_clients))

    options['worker_max_clients'] = max_clients

    if max_clients > 25:
        options['worker_threads_per_child'] = int(max_clients /
                (int(max_clients / 25) + 1))
    else:
        options['worker_threads_per_child'] = max_clients

    options['worker_thread_limit'] = options['worker_threads_per_child']

    count = max_clients / options['worker_threads_per_child']
    options['worker_server_limit'] = int(math.floor(count))
    if options['worker_server_limit'] != count:
        options['worker_server_limit'] += 1

    options['worker_max_clients'] = (options['worker_server_limit'] *
            options['worker_threads_per_child'])

    options['worker_start_servers'] = max(1, int(0.1 *
            options['worker_server_limit']))
    options['worker_min_spare_threads'] = max(
            options['worker_threads_per_child'],
            int(0.2 * options['worker_server_limit']) *
            options['worker_threads_per_child'])
    options['worker_max_spare_threads'] = max(
            options['worker_threads_per_child'],
            int(0.4 * options['worker_server_limit']) *
            options['worker_threads_per_child'])

    options['httpd_conf'] = os.path.join(options['server_root'], 'httpd.conf')

    options['httpd_executable'] = os.environ.get('HTTPD',
            options['httpd_executable'])

    if not os.path.isabs(options['httpd_executable']):
         options['httpd_executable'] = find_program(
                 [options['httpd_executable']], 'httpd', ['/usr/sbin'])

    options['envvars_script'] = (os.path.abspath(
            options['envvars_script']) if options['envvars_script'] is
            not None else None)

    options['httpd_arguments_list'] = []

    if options['startup_log']:
        options['startup_log_filename']= os.path.join(
                options['log_directory'], 'startup.log')

        options['httpd_arguments_list'].append('-E')
        options['httpd_arguments_list'].append(
                options['startup_log_filename'])

    if options['port'] == 80:
        options['url'] = 'http://%s/' % options['host']
    else:
        options['url'] = 'http://%s:%s/' % (options['host'],
            options['port'])

    if options['server_status']:
        options['httpd_arguments_list'].append('-DWSGI_SERVER_STATUS')
    if options['access_log']:
        options['httpd_arguments_list'].append('-DWSGI_ACCESS_LOG')
    if options['keep_alive'] != 0:
        options['httpd_arguments_list'].append('-DWSGI_KEEP_ALIVE')
    if options['multiprocess']:
        options['httpd_arguments_list'].append('-DWSGI_MULTIPROCESS')
    if options['listener_host']:
        options['httpd_arguments_list'].append('-DWSGI_LISTENER_HOST')

    options['httpd_arguments_list'].extend(
            _mpm_module_defines(options['modules_directory']))

    options['httpd_arguments'] = '-f %s %s' % (options['httpd_conf'],
            ' '.join(options['httpd_arguments_list']))

    options['python_executable'] = sys.executable

    generate_apache_config(options)
    generate_control_scripts(options)

    print('Server URL      :', options['url'])

    if options['server_status']:
        print('Server Status   :', '%sserver-status' % options['url'])

    print('Server Root     :', options['server_root'])
    print('Server Conf     :', options['httpd_conf'])

    print('Error Log       :', options['error_log'])

    if options['access_log']:
        print('Access Log      :', os.path.join(options['log_directory'],
    'access_log'))

    return options

def cmd_start_server(params):
    usage = '%prog start-server script [options]'

    options = cmd_setup_server(params, usage)

    executable = os.path.join(options['server_root'], 'server-admin')
    name = executable.ljust(len(options['process_name']))
    os.execl(executable, name, 'start', '-DNO_DETACH')

def cmd_install_module(params):
    formatter = optparse.IndentedHelpFormatter()
    formatter.set_long_opt_delimiter(' ')

    usage = '%prog install-module [options]'
    parser = optparse.OptionParser(usage=usage, formatter=formatter)

    parser.add_option('--modules-directory', metavar='DIRECTORY',
            default=apxs_config.LIBEXECDIR)

    (options, args) = parser.parse_args(params)

    if len(args) != 0:
        parser.error('Incorrect number of arguments.')

    target = os.path.abspath(os.path.join(options.modules_directory,
            MOD_WSGI_SO))

    shutil.copyfile(where(), target)

    print('LoadModule wsgi_module %s' % target)

def cmd_module_location(params):
    formatter = optparse.IndentedHelpFormatter()
    formatter.set_long_opt_delimiter(' ')

    usage = '%prog module-location'
    parser = optparse.OptionParser(usage=usage, formatter=formatter)

    (options, args) = parser.parse_args(params)

    if len(args) != 0:
        parser.error('Incorrect number of arguments.')

    print(where())

main_usage="""
%prog command [params]

Commands:
    install-module
    module-location
    setup-server
    start-server
"""

def main():
    parser = optparse.OptionParser(main_usage.strip())

    args = sys.argv[1:]

    if not args:
        parser.error('No command was specified.')

    command = args.pop(0)

    args = [os.path.expandvars(arg) for arg in args]

    if command == 'install-module':
        cmd_install_module(args)
    elif command == 'module-location':
        cmd_module_location(args)
    elif command == 'setup-server':
        cmd_setup_server(args)
    elif command == 'start-server':
        cmd_start_server(args)
    else:
        parser.error('Invalid command was specified.')

if __name__ == '__main__':
    main()
