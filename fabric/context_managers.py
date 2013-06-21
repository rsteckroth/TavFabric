"""
Context managers for use with the ``with`` statement.

.. note:: When using Python 2.5, you will need to start your fabfile
    with ``from __future__ import with_statement`` in order to make use of
    the ``with`` statement (which is a regular, non ``__future__`` feature of
    Python 2.6+.)
"""

import os
import sys

from contextlib import contextmanager, nested
from fabric.state import env, output, win32

if not win32:
    import termios
    import tty


def _set_output(groups, which):
    """
    Refactored subroutine used by ``hide`` and ``show``.
    """
    # Preserve original values, pull in new given value to use
    previous = {}
    for group in output.expand_aliases(groups):
        previous[group] = output[group]
        output[group] = which
    # Yield control
    yield
    # Restore original values
    output.update(previous)


@contextmanager
def show(*groups):
    """
    Context manager for setting the given output ``groups`` to True.

    ``groups`` must be one or more strings naming the output groups defined in
    `~fabric.state.output`. The given groups will be set to True for the
    duration of the enclosed block, and restored to their previous value
    afterwards.

    For example, to turn on debug output (which is typically off by default)::

        def my_task():
            with show('debug'):
                run('ls /var/www')

    As almost all output groups are displayed by default, `show` is most useful
    for turning on the normally-hidden ``debug`` group, or when you know or
    suspect that code calling your own code is trying to hide output with
    `hide`.
    """
    return _set_output(groups, True)


@contextmanager
def hide(*groups):
    """
    Context manager for setting the given output ``groups`` to False.

    ``groups`` must be one or more strings naming the output groups defined in
    `~fabric.state.output`. The given groups will be set to False for the
    duration of the enclosed block, and restored to their previous value
    afterwards.

    For example, to hide the "[hostname] run:" status lines, as well as
    preventing printout of stdout and stderr, one might use `hide` as follows::

        def my_task():
            with hide('running', 'stdout', 'stderr'):
                run('ls /var/www')
    """
    return _set_output(groups, False)


@contextmanager
def _setenv(**kwargs):
    """
    Context manager temporarily overriding ``env`` with given key/value pairs.

    This context manager is used internally by `settings` and is not intended
    to be used directly.
    """
    previous = {}
    for key, value in kwargs.iteritems():
        if key in env:
            previous[key] = env[key]
        env[key] = value
    try:
        yield
    finally:
        env.update(previous)


def stringify_env_var(var):
    key = result = '$%s' % var
    for value, behaviour, sep in env.get(key, []):
        if behaviour == 'append':
            result = result + sep + '"' + value + '"'
        elif behaviour == 'prepend':
            result = '"' + value + '"' + sep + result
        else:
            result = '"' + value + '"'
    return "%s=%s" % (var, result)


class EnvManager(object):
    """Generator for environment variables-related context managers."""

    cache = {}

    def __init__(self, var):
        self.var = var

    @classmethod
    def for_var(klass, var):
        cache = klass.cache
        if var in cache:
            return cache[var]
        return cache.setdefault(var, klass(var))

    def __str__(self):
        return stringify_env_var(self.var)

    def __call__(
        self, value=None, behaviour='append', sep=os.pathsep, reset=False,
        _valid=frozenset(['append', 'prepend', 'replace'])
        ):
        if value is None:
            return stringify_env_var(self.var)
        if behaviour not in _valid:
            raise ValueError("Unknown behaviour: %s" % behaviour)
        key = '$%s' % self.var
        val = []
        if (not reset) and (behaviour != 'replace'):
            if key in env:
                val.extend(env[key])
        val.append((value, behaviour, sep))
        kwargs = {key: tuple(val)}
        return _setenv(**kwargs)


def settings(*args, **kwargs):
    """
    Nest context managers and/or override ``env`` variables.

    `settings` serves two purposes:

    * Most usefully, it allows temporary overriding/updating of ``env`` with
      any provided keyword arguments, e.g. ``with settings(user='foo'):``.
      Original values, if any, will be restored once the ``with`` block closes.
    * In addition, it will use `contextlib.nested`_ to nest any given
      non-keyword arguments, which should be other context managers, e.g.
      ``with settings(hide('stderr'), show('stdout')):``.

    .. _contextlib.nested: http://docs.python.org/library/contextlib.html#contextlib.nested

    These behaviors may be specified at the same time if desired. An example
    will hopefully illustrate why this is considered useful::

        def my_task():
            with settings(
                hide('warnings', 'running', 'stdout', 'stderr'),
                warn_only=True
            ):
                if run('ls /etc/lsb-release'):
                    return 'Ubuntu'
                elif run('ls /etc/redhat-release'):
                    return 'RedHat'

    The above task executes a `run` statement, but will warn instead of
    aborting if the ``ls`` fails, and all output -- including the warning
    itself -- is prevented from printing to the user. The end result, in this
    scenario, is a completely silent task that allows the caller to figure out
    what type of system the remote host is, without incurring the handful of
    output that would normally occur.

    Thus, `settings` may be used to set any combination of environment
    variables in tandem with hiding (or showing) specific levels of output, or
    in tandem with any other piece of Fabric functionality implemented as a
    context manager.
    """
    managers = list(args)
    if kwargs:
        managers.append(_setenv(**kwargs))
    return nested(*managers)


def cd(path):
    """
    Context manager that keeps directory state when calling operations.

    Any calls to `run`, `sudo` or `local` within the wrapped block will
    implicitly have a string similar to ``"cd <path> && "`` prefixed in order
    to give the sense that there is actually statefulness involved.

    Because use of `cd` affects all such invocations, any code making use of
    `run`/`sudo`/`local`, such as much of the ``contrib`` section, will also be
    affected by use of `cd`. However, at this time, `get` and `put` do not
    honor `cd`; we expect this to be addressed in future releases.

    Like the actual 'cd' shell builtin, `cd` may be called with relative paths
    (keep in mind that your default starting directory is your remote user's
    ``$HOME``) and may be nested as well.

    Below is a "normal" attempt at using the shell 'cd', which doesn't work due
    to how shell-less SSH connections are implemented -- state is **not** kept
    between invocations of `run` or `sudo`::

        run('cd /var/www')
        run('ls')

    The above snippet will list the contents of the remote user's ``$HOME``
    instead of ``/var/www``. With `cd`, however, it will work as expected::

        with cd('/var/www'):
            run('ls') # Turns into "cd /var/www && ls"

    Finally, a demonstration (see inline comments) of nesting::

        with cd('/var/www'):
            run('ls') # cd /var/www && ls
            with cd('website1'):
                run('ls') # cd /var/www/website1 && ls

    .. note::

        This context manager is currently implemented by appending to (and, as
        always, restoring afterwards) the current value of an environment
        variable, ``env.cwd``. However, this implementation may change in the
        future, so we do not recommend manually altering ``env.cwd`` -- only
        the *behavior* of `cd` will have any guarantee of backwards
        compatibility.

    .. note::

        Space characters will be escaped automatically to make dealing with
        such directory names easier.
    """
    path = path.replace(' ', '\ ')
    if env.get('cwd') and not path.startswith('/'):
        new_cwd = env.cwd + '/' + path
    else:
        new_cwd = path
    return _setenv(cwd=new_cwd)


def path(path, behavior='append'):
    """
    Append the given ``path`` to the PATH used to execute any wrapped commands.

    Any calls to `run` or `sudo` within the wrapped block will implicitly have
    a string similar to ``"PATH=$PATH:<path> "`` prepended before the given
    command.

    You may customize the behavior of `path` by specifying the optional
    ``behavior`` keyword argument, as follows:

    * ``'append'``: append given path to the current ``$PATH``, e.g.
      ``PATH=$PATH:<path>``. This is the default behavior.
    * ``'prepend'``: prepend given path to the current ``$PATH``, e.g.
      ``PATH=<path>:$PATH``.
    * ``'replace'``: ignore previous value of ``$PATH`` altogether, e.g.
      ``PATH=<path>``.

    .. note::

        This context manager is currently implemented by modifying (and, as
        always, restoring afterwards) the current value of environment
        variables, ``env.path`` and ``env.path_behavior``. However, this
        implementation may change in the future, so we do not recommend
        manually altering them directly.

    .. versionadded:: 1.0
    """
    warn("Use env.PATH(), path() has been deprecated.")
    return _setenv(path=path, path_behavior=behavior)


def prefix(command):
    """
    Prefix all wrapped `run`/`sudo` commands with given command plus ``&&``.

    This is nearly identical to `~fabric.operations.cd`, except that nested
    invocations append to a list of command strings instead of modifying a
    single string.

    Most of the time, you'll want to be using this alongside a shell script
    which alters shell state, such as ones which export or alter shell
    environment variables.

    For example, one of the most common uses of this tool is with the
    ``workon`` command from `virtualenvwrapper
    <http://www.doughellmann.com/projects/virtualenvwrapper/>`_::

        with prefix('workon myvenv'):
            run('./manage.py syncdb')

    In the above snippet, the actual shell command run would be this::

        $ workon myvenv && ./manage.py syncdb

    This context manager is compatible with `~fabric.context_managers.cd`, so
    if your virtualenv doesn't ``cd`` in its ``postactivate`` script, you could
    do the following::

        with cd('/path/to/app'):
            with prefix('workon myvenv'):
                run('./manage.py syncdb')
                run('./manage.py loaddata myfixture')

    Which would result in executions like so::

        $ cd /path/to/app && workon myvenv && ./manage.py syncdb
        $ cd /path/to/app && workon myvenv && ./manage.py loaddata myfixture

    Finally, as alluded to near the beginning,
    `~fabric.context_managers.prefix` may be nested if desired, e.g.::

        with prefix('workon myenv'):
            run('ls')
            with prefix('source /some/script'):
                run('touch a_file')

    The result::

        $ workon myenv && ls
        $ workon myenv && source /some/script && touch a_file

    Contrived, but hopefully illustrative.
    """
    return _setenv(command_prefixes=env.command_prefixes + [command])


@contextmanager
def char_buffered(pipe):
    """
    Force local terminal ``pipe`` be character, not line, buffered.

    Only applies on Unix-based systems; on Windows this is a no-op.
    """
    if 'disable_char_buffering' in env and env.disable_char_buffering:
        yield
    elif win32 or not sys.stdin.isatty():
        yield
    else:
        old_settings = termios.tcgetattr(pipe)
        tty.setcbreak(pipe)
        try:
            yield
        finally:
            termios.tcsetattr(pipe, termios.TCSADRAIN, old_settings)
