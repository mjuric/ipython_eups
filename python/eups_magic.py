import os, os.path, errno, tempfile
import sys, subprocess, thread
import re, textwrap
import collections

import IPython.display		# for display()
import IPython.utils.process	# for system()

from IPython.utils.warn import (warn, error)

# This will be populated by distrib/make_distrib.sh. Don't change
# the magic value, unless you change it in make_distrib.sh as well.
__version__ = "%%VERSION-NOT-SET-RUNNING-FROM-SOURCE%%"

if sys.platform == 'darwin':
	LD_LIBRARY_PATH='DYLD_LIBRARY_PATH'
else:
	LD_LIBRARY_PATH='LD_LIBRARY_PATH'

# The location of the symlink to default EUPS
#
# This EUPS will be sourced if `%eups init' is called w/o an argument and
# also when the extension is loaded and no EUPS_DIR exists in the
# environment.
#
EUPS_DIR_DEFAULT = os.path.join(os.path.expanduser("~"), '.eups', 'default')

def display(markdown, text=None):
	"""
	Display the given markdown, down-converting it to text
	if no text version of the message is given.
	"""
	data = {}

	# default text to markdown
	if not text:
		text = render_to_plain(markdown)

	if text: 	data['text/plain']    = text
	if markdown:	data['text/markdown'] = markdown

	assert data

	IPython.display.display(data, raw=True)

def update_sys_path(new, old):
	"""
	Update sys.path to reflect the new state of the PYTHONPATH variable.
	"""

	env = dict(os.environ)
	env['PYTHONPATH'] = new

	cmd = """%s -m IPython -c 'import sys;
for p in sys.path:
	print p'
""" % (sys.executable)

	pypath = subprocess.check_output(cmd, shell=True, env=env).split('\n')

	sys.path = pypath

def _purge_linkfarm(libdir):
	"""
	Delete all links from the linkfarm.
	"""
	for fn in os.listdir(libdir):
		fn = os.path.join(libdir, fn)
		if not os.path.islink(fn):
			raise Exception("linkfarm cleanup: the file %s is not a symbolic link. aborting out of caution." % fn )
		os.remove(fn)
	os.rmdir(libdir)

def rebuild_ld_library_path_linkfarm(paths):
	"""
	Populate the dynamic library linkfarm with files found in the
	:-delimited path.

	Any existing linkfarm content will be purged first.
	"""

	# The $linkfarm/lib directory (which is on LD_LIBRARY_PATH) is
	# actually a symlink to the directory where the linkfarm truly is. 
	# Having it be a symlink lets us atomically replace an old linkfarm
	# with a new one.  That avoids race conditions if two IPython
	# instances are trying to rebuild the linkfarm at the same time
	# (possible if, for example, the user is running multiprocessing).

	# Create a new, unique, $linkfarm/lib directory. We will symlink to
	# $linkfarm/lib at the very end.
	linkfarm = os.environ['IPYTHON_EUPS_LIB_LINKFARM']
	dest = tempfile.mkdtemp(prefix='ipython-eups-linkfarm.%d.' % os.getpid(), dir=linkfarm)

	# build the linkfarm from entries on path
	for path in paths.split(':'):
		if not path:
			continue

		# skip anything in the linkfarm directory (i.e.,
		# $linkfarm/lib)
		if path.startswith(linkfarm + os.path.sep):
			continue

		# skip anything that isn't a directory (guard against
		# invalid entries on the LD_LIBRARY_PATH)
		if not os.path.isdir(path):
			continue

		# link all items in paths into the joint path
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


	# atomically repoint $linkfarm/lib to the newly constructed
	# directory. Note how we're creating a new symlink, and then use
	# os.rename() to rename it to 'lib', taking advantage of the fact
	# that renames are atomic on POSIX-compliant filesystems.
	libdir = os.path.join(linkfarm, 'lib')
	oldlibdir = os.path.realpath(libdir) if os.path.exists(libdir) else None

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

	try:
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
	finally:
		# Why do this in a finally clause?
		# a) we want to print out the messages about eups_loc and
		#    the message about EUPS_PATH in the same Markdown block,
		#    so they look nice on the screen.
		# b) but we also want the message about eups_loc to be printed
		#    no matter what, so the user is given information about where
		#    eups is being loaded from in case anything went wrong.
		msg = "**``%%eups init:``** loading EUPS from `%s`." % eups_loc
		if 'EUPS_PATH' in os.environ:
			msg += "  \n**``%%eups init:``** using `EUPS_PATH=%s`." % os.environ['EUPS_PATH']
		display(msg)

	if eups_loc != EUPS_DIR_DEFAULT:
		if set_default:
			if os.path.islink(EUPS_DIR_DEFAULT):
				os.unlink(EUPS_DIR_DEFAULT)

			msg="**``%%eups init:``** symlinking `%s` -> `%s`" % (EUPS_DIR_DEFAULT, eups_loc)
			display(msg)

			os.symlink(eups_loc, EUPS_DIR_DEFAULT)
		elif not os.path.islink(EUPS_DIR_DEFAULT):
			display("**``%%eups init:``** To make this default, rerun with ``%%eups init --set-default %s``" % eups_loc)

def _get_setuped_product_version(product):
	"""
	Returns the setup-ed version of <product>
	"""
	try:
		setupcmd = "eups list -s %s" % product
		ret = subprocess.check_output(setupcmd, stderr=subprocess.STDOUT, shell=True)
		return ret.rstrip().split()[0]
	except subprocess.CalledProcessError as e:
		return None

def eups(line):
	"""\
	Setup and unsetup EUPS products from within IPython

	Common usage:

	    # Set up a product
	    %eups setup <product>

	    # Unsetup a product
	    %eups unsetup <product>

	If no EUPS has been setup (i.e., you didn't source setups.sh before
	starting IPython), the default EUPS will be set up once this
	extension is loaded with %load_ext. You can also set it up manually
	with %eups init (see below).

	More examples:

	    # Initialize EUPS
	    %eups init [[--set-default] path_to_eups [EUPS_PATH]]

	    # Version of ipython_eups script
	    %eups version

	    # EUPS subcommands are passed on to EUPS
	    %eups list
	    %eups --version

	More documentation on http://github.com/mjuric/ipython_eups.
	"""

	split = line.split()
	cmd, args = split[0], split[1:]

	if cmd == "unsetup":
		cmd = "setup"
		args.insert(0, '--unsetup')
		unsetup = True
	else:
		unsetup = False

	if cmd == "init":
		# find the '--set-default' flag
		set_default = '--set-default' in args
		if set_default:
			args.remove('--set-default')
		return init_eups(*args, set_default=set_default)
	elif cmd == "setup":
		# run 'setup'
		args2 = [ arg for arg in args if not arg.startswith('-') ]
		product = args2[0] if args2 else None

		# If this is an unsetup call, remember the version for printing at the end
		if unsetup:
			version = _get_setuped_product_version(product)

		setupimpl = os.path.join(os.environ['EUPS_DIR'], 'bin/eups_setup_impl.py')
		setupcmd = "python '%s' %s" % (setupimpl, ' '.join(args))

		try:
			ret = subprocess.check_output(setupcmd, stderr=subprocess.STDOUT, shell=True).strip()
		except subprocess.CalledProcessError as e:
			error("%s\n%s" % (str(e), e.output))
		else:
			if product is None:
				# If the user ran something like 'setup -h', just print out the result
				print ret
			else:
				ret = ret.split('\n')
				if not len(ret) or ret[-1] == 'false':
					# setup failed; return the error message
					error(str('\n'.join(ret[:-1])))
				else:
					exportRe = re.compile('export\s+(\w+)=(.*?);?$')
					unsetRe  = re.compile('unset\s+(\w+);?$')
					export = collections.OrderedDict()
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

				if not unsetup:
					version = _get_setuped_product_version(product)

				# print out some useful info about what we've just setup-ed
				msg = "**``%%eups %s:``** `%s`, version `%s`" % ('setup' if not unsetup else 'unsetup', product, version)
				display(msg)
	elif cmd == "version":
		msg = "**``%%eups version:``** `%s`" % (__version__)
		display(msg)
	else:
		setupcmd = "eups %s %s" % (cmd, ' '.join(args))
		
		IPython.utils.process.system(setupcmd)

def load_ipython_extension(ipython):
	"""
	Load the %eups extension. IPython extension API entry point.
	"""

	# Sanity checks. Do as many of these as necessary, to make sure we catch issues
	# early on that may cause difficult-to-debug misbehaviors later.
	#
	# Refuse to proceed if there's no pointer to the linkfarm in the environment,
	# or the linkfarm doesn't exist, or the linkfarm dir isn't in LD_LIBRARY_PATH.
	# The most likely cause of this is not having started ipython via the
	# supplied 'ipython' wrapper script, or some bug in the wrapper itself.
	if 'IPYTHON_EUPS_LIB_LINKFARM' not in os.environ:
		raise Exception(textwrap.dedent("""\
			It looks like IPython hasn't been started using the 'ipython' wrapper
			script supplied by ipython_eups. Maybe you forgot to add it to your path?
			
			Guru Meditation: IPYTHON_EUPS_LIB_LINKFARM environmental variable has not
			been set. The aforementioned wrapper script sets this variable before
			calling IPython.
		""").replace('\n', ' ').replace('  ', '\n\n'))

	linkfarm = os.environ['IPYTHON_EUPS_LIB_LINKFARM']
	if not os.path.isdir(linkfarm):
		raise Exception(textwrap.dedent("""\
			Something is amiss with how ipython_eups has been started; directories
			that are needed for %eups to work don't exist. Try restarting IPython
			and see if the problem clears up.
			
			Guru Meditation: The directory that IPYTHON_EUPS_LIB_LINKFARM
			environmental variable points to -- %(linkfarm)s -- does not exist. This
			directory is supposed to be created by the 'ipython' wrapper script.
		""" % { 'linkfarm': linkfarm } ).replace('\n', ' ').replace('  ', '\n\n'))

	if LD_LIBRARY_PATH not in os.environ:
		raise Exception(textwrap.dedent("""\
			Something is amiss with ipython_eups. Try restarting IPython and see if
			the problem clears up.
			
			Guru Meditation: The %(lddir)s environment variable has not been set.
			This variable was supposed to be created by the 'ipython' wrapper script.
			You may have uncovered a bug in the wrapper script.
		""" % { 'lddir': LD_LIBRARY_PATH } ).replace('\n', ' ').replace('  ', '\n\n'))

	liblinkfarm = os.path.join(linkfarm, 'lib')
	if liblinkfarm not in os.environ[LD_LIBRARY_PATH].split(':'):
		print os.environ[LD_LIBRARY_PATH].split(':')
		raise Exception(textwrap.dedent("""\
			Something is amiss with ipython_eups. Try restarting IPython and see if
			the problem clears up.
			
			Guru Meditation: The "library linkfarm" directory exists [== %(linkfarm)s], but
			isn't on %(lddir)s [== %(ldpath)s]. It was supposed to be added to it by
			the 'ipython' wrapper script. This may be a bug in the wrapper script.
		""" % { 'lddir': LD_LIBRARY_PATH, 'linkfarm' : liblinkfarm, 'ldpath' : os.environ[LD_LIBRARY_PATH] } 
		    ).replace('\n', ' ').replace('  ', '\n\n'))


	# Re-initialize the link farm every time IPython is started, so that the environment
	# is properly cleaned of any left-overs from prior runs. E.g., this may happen
	# when IPython notebook kernel is restarted by the user.
	rebuild_ld_library_path_linkfarm(os.environ[LD_LIBRARY_PATH])

	#print "-----------------------------------------------------------------------"
	#print "Note to readers: if you don't have ipython_eups installed, get it from"
	#print "     http://github.com/mjuric/ipython_eups to enable eups_magic."
	#print "-----------------------------------------------------------------------"

	# Register %eups magic
	ipython.register_magic_function(eups)

	display("``%eups`` magics loaded. Documentation and source at http://github.com/mjuric/ipython_eups.")

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


#################################################################################
# Simple Markdown -> text/plain parser, based on
# https://gist.github.com/possatti/8918a324fa83acbd191b
# by Lucas Possatti
#

plain_rules = collections.OrderedDict()
plain_rules[r'\[([^\[]+)\]\(([^\)]+)\)'] = r'\1 (at \2)' # links
plain_rules[r'(\*\*|__)(.*?)\1'] = r'\2' # bold
plain_rules[r'(\*|_)(.*?)\1'] = r'\2' # emphasis
plain_rules[r'\~\~(.*?)\~\~'] = r'\1' # del
plain_rules[r'\:\"(.*?)\"\:'] = r'\1' # quote
plain_rules[r'`(.*?)`'] = r'\1' # inline code
plain_rules[r'\n-{5,}'] = r"\n" + 40*"-" + "\n" # horizontal rule

def render_to_plain(text):
	text = '\n' + text + '\n'
	for regex, replacement in plain_rules.items():
		text = re.sub(regex, replacement, text)
	return text.strip()

#################
### Debugging ###
#################

if False and __name__ == '__main__':
	input_text = sys.stdin.read()
	rendered_text = render_to_plain(input_text)
	print rendered_text
