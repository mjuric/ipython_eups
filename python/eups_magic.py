from IPython.core.magic import (register_line_magic, register_cell_magic, register_line_cell_magic)
import marshal, os, subprocess, sys, errno, tempfile, IPython, thread
from IPython.utils.warn import (warn, error, info)
import textwrap

if sys.platform == 'darwin':
	LD_LIBRARY_PATH='DYLD_LIBRARY_PATH'
else:
	LD_LIBRARY_PATH='LD_LIBRARY_PATH'

EUPS_DIR_DEFAULT = os.path.join(os.path.expanduser("~"), '.eups', 'default')

def update_sys_path(new, old):
	# update sys.path to reflect the new state of the PYTHONPATH
	# variable, while retaining

	env = dict(os.environ)
	env['PYTHONPATH'] = new

	cmd = """%s -m IPython -c 'import sys;
for p in sys.path:
	print p'
""" % (sys.executable)

	pypath = subprocess.check_output(cmd, shell=True, env=env).split('\n')

	sys.path = pypath

def _purge_linkfarm(libdir):
	# delete the directory
	for fn in os.listdir(libdir):
		fn = os.path.join(libdir, fn)
		if not os.path.islink(fn):
			raise Exception("linkfarm cleanup: the file %s is not a symbolic link. aborting out of caution." % fn )
		os.remove(fn)
	os.rmdir(libdir)

def rebuild_ld_library_path_linkfarm(paths):
	# Make sure we have a linkfarm to work with
	try:
		linkfarm = os.environ['IPYTHON_EUPS_LIB_LINKFARM']
	except KeyError:
		error(
			("The product you're setting up is attempting to modify %s, and\n" +
			"IPython hasn't been started via the ipython_eups wrapper. It's likely that the\n" +
			"product won't be setup-ed correctly, so I'm refusing to prceed.\n\n" +
			"Maybe you forgot to `setup ipython_eups' before starting ipython?") % LD_LIBRARY_PATH
		)
		return

	# create a temporary $linkfarm/lib directory
	dest = tempfile.mkdtemp(prefix='ipython-eups-linkfarm.%d.' % os.getpid(), dir=linkfarm)

	# link all items in paths into the joint path
	for path in paths.split(':'):
		if not path:
			continue

		if path.startswith(linkfarm + os.path.sep):
			continue

		if not os.path.isdir(path):
			continue

#		print "LINKING: %s" % path
#		print "     LF: %s" % linkfarm

		path = os.path.realpath(path)
		for fn in os.listdir(path):
			src = os.path.join(path, fn)
			lnk = os.path.join(dest, fn)
			try:
				os.symlink(src, lnk)
			except OSError as e:
				# Skip over links that already exist. Items from directories 
				# earlier on the path will shadow those that come later.
				if e.errno != errno.EEXIST:
					raise


	libdir = os.path.join(linkfarm, 'lib')
	oldlibdir = os.path.realpath(libdir) if os.path.exists(libdir) else None

	# atomic replacement of the old directory
	tmplink = '%s.%d.%d' % (dest, thread.get_ident(), os.getpid())	# Unique temporary name
	os.symlink(os.path.basename(dest), tmplink)
	os.rename(tmplink, libdir)

	# delete the old directory; ignore any errors that may be encountered. as
	# those can come from race conditions if (say) two threads are trying to delete
	# the same directory (should be _very_ uncommon, though).
	try:
		if oldlibdir is not None:
			_purge_linkfarm(oldlibdir)
	except Exception as e:
		warn(str(e))

def init_eups(eups_loc='default', eups_path=None, set_default=False):
	"""
		If the user forgot to run setups.sh, initialize EUPS
		from scratch. Do it by running setups.sh and replacing our
		current environment with the environment it will generate.
		
		Arguments:
		
		   eups_loc:    directory where EUPS is installed (where 
		                bin/setups.sh will be found). If not
		                given, a default from ~/.eups/default
		                will be assumed

		   eups_path:   The location of the EUPS product stack 
		                (EUPS_PATH environment variable). Optional.
		
		   set_default: If set, eups_loc will be symlinked to
		   		~/.eups/default.
	"""

	# Locate EUPS
	if eups_loc == 'default':
		if not os.path.isdir(EUPS_DIR_DEFAULT):
			error(textwrap.dedent("""\
				You're trying to initialize EUPS without specifying its location,
				and the default in %(default)s does not exist (or is inaccessible).
				
				Either rerun the command as '%%eups init <eups_location>', or symlink
				the path to EUPS (the location where 'bin/setups.sh' can be found)
				as %(default)s .
			""" % { 'default': EUPS_DIR_DEFAULT } ).replace('\n', ' ').replace('  ', '\n\n'))
			return
		else:
			eups_loc = EUPS_DIR_DEFAULT

	# Verify that EUPS exists
	setups_sh = os.path.join(eups_loc, 'bin', 'setups.sh')
	if not os.path.isfile(setups_sh):
		error(textwrap.dedent("""\
			Cannot find %s.
			
			Are you sure that EUPS has been installed in %s?
		""" % (setups_sh, eups_loc) ).replace('\n', ' ').replace('  ', '\n\n'))
		return

	info("Initializing EUPS from %s" % eups_loc)

	# Load the environment
	cmd = r"""
source %(setups_sh)s >/dev/null
%(python)s -c '
import os, sys;
for k, v in os.environ.iteritems():
    sys.stdout.write("%%s\0%%s\0" %% (k, v))
'""" % { 'python' : sys.executable, 'setups_sh' : setups_sh }

	envl = subprocess.check_output(cmd, shell=True).split('\0')
	env = { k: v for k, v in zip(envl[::2], envl[1::2]) }

	os.environ.clear()
	os.environ.update(dict=env)

	# Override EUPS_PATH, if requested
	if eups_path is not None:
		os.environ['EUPS_PATH'] = eups_path

	info("Using EUPS_PATH: %s" % os.environ['EUPS_PATH'])

	if eups_loc != EUPS_DIR_DEFAULT:
		if set_default:
			if os.path.islink(EUPS_DIR_DEFAULT):
				os.unlink(EUPS_DIR_DEFAULT)
			os.symlink(eups_loc, EUPS_DIR_DEFAULT)
			info("Setting as default: %s symlinked to %s" % (eups_loc, EUPS_DIR_DEFAULT))
		elif not os.path.islink(EUPS_DIR_DEFAULT):
			info("To set this EUPS as default, rerun as `%%eups init --set-default %s'" % eups_loc)

# Re-initialize the link farm every time IPython is started, so that the environment
# is properly cleaned of any left-overs from prior runs. E.g., this may happen
# when IPython notebook kernel is restarted by the user.
if 'IPYTHON_EUPS_LIB_LINKFARM' in os.environ and LD_LIBRARY_PATH in os.environ:
	rebuild_ld_library_path_linkfarm(os.environ[LD_LIBRARY_PATH])

def eups(line):
	"my line magic"

	import sys, os, os.path, re
	import subprocess
	from collections import OrderedDict

	from IPython import display

	split = line.split()
	cmd, args = split[0], split[1:]

	if cmd == "unsetup":
		cmd = "setup"
		args.insert(0, '--unsetup')

	if cmd == "init":
		# find the '--set-default' flag
		set_default = '--set-default' in args
		if set_default:
			args.remove('--set-default')
		return init_eups(*args, set_default=set_default)
	elif cmd == "setup":
		# run 'setup'
		setupimpl = os.path.join(os.environ['EUPS_DIR'], 'bin/eups_setup_impl.py')
		setupcmd = "python '%s' %s" % (setupimpl, ' '.join(args))

		try:
			ret = subprocess.check_output(setupcmd, stderr=subprocess.STDOUT, shell=True).strip().split('\n')
		except subprocess.CalledProcessError as e:
			error("%s\n%s" % (str(e), e.output))
		else:
			if not len(ret) or ret[-1] == 'false':
				# setup failed; return the error message
				error(str('\n'.join(ret[:-1])))
			else:
				exportRe = re.compile('export\s+(\w+)=(.*?);?$')
				unsetRe  = re.compile('unset\s+(\w+);?$')
				export = OrderedDict()
				unset  = set()
				for line in ret[:-1]:
					m = exportRe.match(line)
					if m:
						export[m.group(1)] = m.group(2)
						continue

					m = unsetRe.match(line)
					if m:
						unset.add(m.group(1))
						continue
				
					error("EUPS told me to '%s' but I don't know how to handle that. Aborting." % (line))

				# do the variable (un)setups. We do this only after
				# the entire output is processed above, to avoid
				# aborting half-way in case of errors (and leaving
				# the environment in an incoherent state).

				for var, value in export.iteritems():
					value = subprocess.check_output('/bin/echo -n %s' % value, shell=True)
					if var == "PYTHONPATH":
						update_sys_path(value, os.environ[var])
					if var == LD_LIBRARY_PATH:
						rebuild_ld_library_path_linkfarm(value)
					os.environ[var] = value
					#print "set: %s=[%s]" % (var, os.environ[var])
				for var in unset:
					#print "unset: " + var
					del os.environ[var]
	else:
		setupcmd = "eups %s %s" % (cmd, ' '.join(args))

		# run EUPS
		try:
			ret = subprocess.check_output(setupcmd, stderr=subprocess.STDOUT, shell=True).rstrip()
			print ret
		except subprocess.CalledProcessError as e:
			error("%s\n%s" % (str(e), e.output))

def load_ipython_extension(ipython):
	# The `ipython` argument is the currently active `InteractiveShell`
	# instance, which can be used in any way. This allows you to register
	# new magics or aliases, for example.
	ipython.register_magic_function(eups)

	# Check if EUPS has been setup, if not, try to set it up
	# from the default environment.
	if 'EUPS_DIR' not in os.environ:
		if os.path.isdir(EUPS_DIR_DEFAULT):
			init_eups()
		else:
			warn(("EUPS not initialized, and no default EUPS has been symlinked as %s. " +
			      "Make sure to initialize it with `%%eups init <path_to_eups>'") % EUPS_DIR_DEFAULT)

#def unload_ipython_extension(ipython):
#	# If you want your extension to be unloadable, put that logic here.
