from IPython.core.magic import (register_line_magic, register_cell_magic, register_line_cell_magic)
import marshal, os, subprocess, sys, errno, tempfile, IPython

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

def _purge_linkfarm(dest):
	# clean the directory
	for fn in os.listdir(dest):
		fn = os.path.join(dest, fn)
		if not os.path.islink(fn):
			raise Exception("linkfarm cleanup: the file %s is not a symbolic link. aborting for safety reasons." % fn )
		os.remove(fn)

def build_library_linkfarm(paths):
	paths = paths.split(':')

	dest = os.path.realpath(os.environ["EUPS_LIB_LINKFARM"])

	_purge_linkfarm(dest)

	# link all items in paths into the joint path
	for path in reversed(paths):
		path = os.path.realpath(path)

		if path == dest:
			continue

		if not os.path.isdir(path):
			continue

		for fn in os.listdir(path):
			src = os.path.join(path, fn)
			lnk = os.path.join(dest, fn)
			try:
				os.symlink(src, lnk)
			except OSError as e:
				if e.errno != errno.EEXIST:
					raise

# inspired by http://stackoverflow.com/a/5227009/897575
def which(fn):
	for path in os.environ["PATH"].split(":"):
		path = os.path.join(path, fn)
		if os.path.exists(path):
			return path
	return None

def inject_linkfarm_library_path(linkfarmPath):
	"""
	Inject the link farm path into (DY)LD_LIBRARY_PATH.
	
	Dynamic linker reads LD_LIBRARY_PATH only on program execution, and
	is unaffected by changes to it made at runtime (e.g., with putenv()).

	Therefore, we need to add the link farm path to LD_LIBRARY_PATH as
	early in the execution as possible, and re-exec ourselves using
	execve().  Alas, when executing startup scripts, IPython changes the
	contents of sys.path to make it appear as if the scripts were run
	from the command line, so we can't use it to figure out what to
	execv.  We therefore use 'ps -o command -p' to find the original
	command line that IPython was run with, and execv that.
	
	Known issues:

	  * If the original command line contains whitespaces, this will
	    fail.
	
	"""

	env = dict(os.environ)
	env['EUPS_LIB_LINKFARM'] = os.path.realpath(linkfarmPath)
	env['DYLD_LIBRARY_PATH'] = linkfarmPath + ':' + env.get('DYLD_LIBRARY_PATH', '')

	# find our true command line
	pid = os.getpid()
	argv = subprocess.check_output('ps -o command= -p %d' % pid, shell=True).split()

	# Avoid having IPython write out the banner once it's restarted
	if is_console:
		argv += [ '--no-banner' ]

	cmd = which(argv[0])
	##print pid, cmd, argv, " (DYLD_LIBRARY_PATH=%s)." % os.environ['DYLD_LIBRARY_PATH']

	# re-execute ourselves.
	if is_console:
		print
		print "eups-magic: injecting %s onto (DY)LD_LIBRARY_PATH." % linkfarmPath
	os.execve(cmd, argv, env)

is_console = isinstance(IPython.get_ipython(), IPython.terminal.interactiveshell.TerminalInteractiveShell)

if True:
	_inject = True
	if 'EUPS_LIB_LINKFARM' in os.environ and 'DYLD_LIBRARY_PATH' in os.environ:
		linkfarm = os.path.realpath(os.environ["EUPS_LIB_LINKFARM"])
		ldpaths = os.environ['DYLD_LIBRARY_PATH'].split(':')
		if len(ldpaths) and os.path.realpath(ldpaths[0]) == linkfarm:
			_inject = False

	if _inject:
		linkfarmPath = tempfile.mkdtemp(prefix='eups-linkfarm')
		inject_linkfarm_library_path(linkfarmPath)

	_purge_linkfarm(linkfarm)
	if is_console:
		print "eups-magic: (DY)LD_LIBRARY_PATH=%s." % os.environ['DYLD_LIBRARY_PATH']
	build_library_linkfarm(os.environ['DYLD_LIBRARY_PATH'])

#build_library_linkfarm('/Users/mjuric/projects/eups/stack/DarwinX86/oorb/lsst-g650e0a6f6c/lib:/Users/mjuric/projects/eupsforge/ups_db/DarwinX86/node/master-g585d2d3511/ups')
#exit()

@register_line_magic
def eups(line):
	"my line magic"

	import sys, os, os.path, re
	import subprocess
	from collections import OrderedDict

	from IPython import display
	from IPython.utils.warn import (warn, error)

	split = line.split()
	cmd, args = split[0], split[1:]

	if cmd == "unsetup":
		cmd = "setup"
		args.insert(0, '--unsetup')

	if cmd == "setup":
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
					if var == "DYLD_LIBRARY_PATH":
						build_library_linkfarm(value)
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
