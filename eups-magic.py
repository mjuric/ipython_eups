from IPython.core.magic import (register_line_magic, register_cell_magic, register_line_cell_magic)
import marshal, os, subprocess, sys, errno, tempfile, IPython, thread

if sys.platform == 'darwin':
	LD_LIBRARY_PATH='DYLD_LIBRARY_PATH'
else:
	LD_LIBRARY_PATH='LD_LIBRARY_PATH'

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
		from IPython.utils.warn import error
		error(
			"The product you're setting up is attempting to modify %s, and\n" +
			"IPython hasn't been started with ipython_eups support. It's likely that the\n" +
			"product won't be setup-ed correctly.\n\n" +
			"Maybe you forget to `setup ipython_eups' before starting ipython?" % LD_LIBRARY_PATH
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
		from IPython.utils.warn import warn
		warn(str(e))

# Re-initialize the link farm every time IPython is started, so that the environment
# is properly cleaned of any left-overs from prior runs. E.g., this may happen
# when IPython notebook kernel is restarted by the user.
if 'IPYTHON_EUPS_LIB_LINKFARM' in os.environ and LD_LIBRARY_PATH in os.environ:
	rebuild_ld_library_path_linkfarm(os.environ['LD_LIBRARY_PATH'])

#rebuild_ld_library_path_linkfarm('/Users/mjuric/projects/eups/stack/DarwinX86/oorb/lsst-g650e0a6f6c/lib:/Users/mjuric/projects/eupsforge/ups_db/DarwinX86/node/master-g585d2d3511/ups')
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
