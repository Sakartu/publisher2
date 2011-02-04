#!/usr/bin/env python
import urllib
import os
import getopt
import ConfigParser
import sys
import zipfile
import tarfile
import paramiko
from out_server import out_server
from pub_object import pub_object
from process import process
import tempfile
import random
import shutil
import getpass
import traceback
import sftp_wrap

'''

notes

the main method proceeds with the following steps:
	- parse all input options, create from them an eventchain (list) 
	of functions that will be called on the set of inputobjects before the
	final function is applied
	- parse all input objects, create from them in_object's  
	- parse one (or multiple) output objects, create from them out_object's
	- apply all preprocess functions
	- apply the final function and return result

'''

# a dictionary of cmdline options to process objects
func_dict = {}

#a list tuples containing mututally exclusive functions, tuple[0] takes presedence
mut_ex_func = []

#a list of input/output objects
objects = []

#the output location
out = None

#a temporary directory in which we can write
tempdir = None

#the chain of processes that will be run, will be sorted 
process_chain = []

#configuration stuff
conf_file = "/etc/publish.conf"
conf = None

#toggles indicating various behaviour
verbose = False
test_run = False
recur_dir = False

def main():
	global process_chain, objects, tempdir
	#we first parse all the commandline options
	parse_options(sys.argv)
	#parse_options(["publisher2", "-szTrv", "poep", "test2/file", "test1", "spooky"])

	log("Running stage 0 processes")
	#then we run the stage 0 processes such as verbosity and usage prints
	run_procs(0)

	log("Running stage 1 processes")
	#and run the stage 1 processes which set a lot of toggles
	run_procs(1)

	#then we parse the conf file
	parse_conf()

	#time to get busy, we have a list of interesting objects, let's find out
	#what the destination should be
	if len(objects) == 0 :
		#no input whatsoever, we read from stdin and output to pastebin
		proc_stdin()
	elif len(objects) == 1 :
		#single commandline argument, we use the config default as out
		set_out()
	else:
		#multiple outputs, the last argument is the out, set it, then remove it from the list
		set_out(objects[-1])
		objects = objects[:-1]

	log("Running stage 2 processes...")
	#our inputs and output are available, time to run stage 2 processes
	run_procs(2)

	#if all went well, we now have some input in objects, time to send it over to the serv
	send_files()

	log("Running stage 3 processes...")
	#everything sent, time for phase 3
	run_procs(3)
	
	log("Performing cleanup...")
	#perform cleanup if necessary
	if tempdir != None :
		shutil.rmtree(tempdir, ignore_errors=True)

def parse_conf():
	global conf
	conf = ConfigParser.SafeConfigParser()
	log("Looking for conf file in " + conf_file)
	if(os.access(conf_file, os.F_OK) and os.access(conf_file, os.W_OK)):
		conf.read(conf_file)
	else:
		print "No configfile found, aborting!"
		exit(-1)

def proc_stdin():
	print "yay"

def proc_verb():
	global verbose
	verbose = True
	
def proc_help():
	usage(exit, 0)

def proc_test():
	global test_run
	test_run = True
	
def proc_recur():
	global recur_dir
	recur_dir = True
	
def proc_conf(location):
	global conf_file
	conf_file = location
	
def proc_shorten():
	log("Shortening url's...")
	if conf.has_key("bit.ly", "username") and conf.has_key("bit.ly", "api_key"):
		user = conf.get("bit.ly", "username")
		api_key = conf.get("bit.ly", "api_key")
		for obj in objects:
			try:
				encoded_long_url = urllib.quote_plus(obj.remote_loc)
				url="http://api.bit.ly/v3/shorten?longURL=%s&login=%s&apiKey=%s&format=txt" % (encoded_long_url, user, api_key)
				request = urllib.urlopen(url)
				responde = request.read()
				request.close()
				return responde

			except IOError, e:
				print "Could not shorten url, service down?"
	else:
		print "No bit.ly credentials found in config!"


def proc_tar():
	#before we start anything, we need to be sure that we have some place to put temporary files
	global tempdir, objects
	tempdir = os.path.join(tempfile.gettempdir(), rnd_str(10))
	os.makedirs(tempdir)
	if len(objects) > 0:
		tar_file_name = os.path.join(tempdir, os.path.basename(objects[0].location) + ".tar.gz")
		tfile = tarfile.open(tar_file_name, mode='w:gz')
		#we have a tarfile object, let's start putting stuff in
		for o in objects:
			log("Tarring file \"" + o.location + "\"...")
			tfile.add(o.location, recursive=recur_dir)
		objects = [pub_object(tar_file_name)]
		
def proc_zip():
	#before we start anything, we need to be sure that we have some place to put temporary files
	global tempdir, objects
	tempdir = os.path.join(tempfile.gettempdir(), rnd_str(10))
	os.makedirs(tempdir)
	if len(objects) > 0:
		zip_file_name = os.path.join(tempdir, os.path.basename(objects[0].location) + ".zip")
		zfile = zipfile.ZipFile(zip_file_name, mode='w')
		#we have a zipfile object, let's start putting stuff in
		for o in objects:
			log("Zipping file \"" + o.location + "\"...")
			zip_object(zfile, o.location)
		objects = [pub_object(zip_file_name)]
		print zip_file_name

def zip_object(archive, o):
	if os.path.isdir(o):
		paths = os.listdir(o)
		for p in paths:
			p = os.path.join(o, p) # Make the path relative
			if os.path.isdir(p): # Recursive case
				zip_object(p, archive)
			else:
				archive.write(p) # Write the file to the zipfile
	else:
		archive.write(o)
		
def proc_pbin():
	pass

def send_files():
	#print out.username + "@" + out.hostname + ":" + out.remotedir
	#we already have username, hostname and remotedir, let's find some secretes
	#first we check for host keys, as they are most convenient
	hostkeytype = None
	hostkey = None
	try:
		host_keys = paramiko.util.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'))
	except IOError:
		try:
			# try ~/ssh/ too, because windows can't have a folder named ~/.ssh/
			host_keys = paramiko.util.load_host_keys(os.path.expanduser('~/ssh/known_hosts'))
		except IOError:
			log("Unable to open host keys file, asking password")
			host_keys = {}

	if host_keys.has_key(out.hostname):
		hostkeytype = host_keys[out.hostname].keys()[0]
		hostkey = host_keys[out.hostname][hostkeytype]
		print 'Using host key of type %s' % hostkeytype
	if(out.password == ""):
		#if no password available in the config, ask for a password
		out.password = getpass.getpass("No password or hostfile available, enter password [<enter> for empty]: ")

	try:
		log("Trying to connect to \"" + out.username + "@" + out.hostname + ":" + out.remotedir + "\"...")
		t = paramiko.Transport((out.hostname, out.port))
		t.connect(username=out.username, password=out.password, hostkey=hostkey)
		sftp = paramiko.SFTPClient.from_transport(t)
		log("Done.")

		#start the actual upload
		for obj in objects:
			log("cwd = " + os.getcwd())
			log("Sending over \"" + obj.location + "\"...")
			sftp_wrap.put(sftp, os.path.abspath(obj.location), out.remotedir)
			if os.path.isdir(obj.location):
				#transfer succeeded, save the place where it can be found
				obj.remote_loc = os.path.join(out.url_prefix, obj.location)
			else:
				#transfer succeeded, save the place where it can be found
				obj.remote_loc = os.path.join(out.url_prefix, os.path.basename(obj.location))

	except Exception, e:
		print '*** Caught exception: %s: %s' % (e.__class__, e)
		traceback.print_exc()
		try:
			t.close()
		except:
			pass
		sys.exit(1)
		#print "Connection troubles, couldn't upload file!"
		#try:
		#	t.close()
		#except:
		#	pass
		#exit(-1)

def fix_chain():
	global process_chain
	#first we remove any mutually excusive options, using the mut_ex_func list
	#if fst and snd occur as run in a process in the chain, remove snd
	for (fst, snd) in mut_ex_func:
		process_chain = filter(lambda x : x.run != snd or len([y for y in process_chain if y.run == fst]) == 0, process_chain)
	
	#then we sort the remaining list
	process_chain = sorted(process_chain, lambda x, y : cmp(x.stage, y.stage))

def set_out(out_obj=None):
	global out
	if out_obj != None:
		serv_alias = out_obj.location
	elif conf != None and conf.has_option("defaults", "server"):
		serv_alias = conf.get("defaults", "server")
	else:
		print "No server specified and no default server available!"
		exit(-1)

	if conf.has_option("servers", serv_alias) and conf.has_option("locations", serv_alias):
		out = out_server(conf.get("servers", serv_alias), conf.get("locations", serv_alias))
	else:
		print "Server \"" + serv_alias + "\" was specified, but credentials were not available in configfile!"
		exit(-1)
	
def run_procs(stage):
	for proc in [x for x in process_chain if x.stage == stage]:
		log("Running stage 0 process " + proc.run.__name__)
		if(proc.args != ""):
			proc.run(proc.args)
		else:
			proc.run()

def log(msg, postfunc=None, postargs=None):
	if(verbose == True):
		print msg
	if postfunc != None:
		postfunc(postargs)

def parse_options(argv):
	global func_dict, process_chain, mut_ex_func
	func_dict = {	
		'-s' : lambda a : process(proc_shorten,		a, 3, "-s",			"Shorten url using bit.ly"),
		'-t' : lambda a : process(proc_tar,			a, 2, "-t",			"Tar and gzip input before sending"),
		'-z' : lambda a : process(proc_zip,			a, 2, "-z",			"Zip input before sending, takes precedence over -t"),
		'-p' : lambda a : process(proc_pbin,		a, 2, "-p",			"Put input on pastebin, takes precedence over -t and -z"),
		'-T' : lambda a : process(proc_test,		a, 1, "-T",			"Perform a test run"),
		'-r' : lambda a : process(proc_recur,		a, 1, "-r or -R",		"Handle directories recursive"),
		'-R' : lambda a : process(proc_recur,		a, 1, "-r or -R",		"Handle directories recursive"),
		'-c:': lambda a : process(proc_conf,		a, 1, "-c <file>",		"Use <file> as configfile"),
		'-v' : lambda a : process(proc_verb,		a, 0, "-v",			"Increase verbosity"),
		'-h' : lambda a : process(proc_help,		a, 0, "-h",			"Show this help"),
			}

	functions  = lambda o, a : (func_dict[o] if o in func_dict else func_dict[o + ":"])(a)

	available_cli_options = reduce(lambda x, y: x + y, func_dict.keys())

	try:
		optlist, args = getopt.gnu_getopt(argv[1:], available_cli_options)
	except getopt.GetoptError as oe:
		log("Error, option \"-" + oe.opt + "\" is not available!\n")
		usage(exit, 0)

	for o, a in optlist:
		process_chain.append(functions(o, a))
	
	if(len(args) > 0):
		for arg in args:
			objects.append(pub_object(arg))

	#we now know which process to run, they are in process_chain, but they are unsorted
	#and may contain mutual exclusive options. before we can do anything, we need to
	#remove the mutually exclusive options and sort them. first we make a list of these
	#options, the first in the tuple takes precedence over the second
	mut_ex_func = [
	(proc_zip, proc_tar),		#if you zip, you can't tar
	(proc_pbin, proc_zip),		#if you pastebin, you can't zip
	(proc_pbin, proc_tar)		#or tar
			]
	#then we filter out all mutex functions
	fix_chain()

def usage(postfunc=None, postargs=None):
	print "Usage: publish [options] [(file/dir)+] ([[user@]host] | [hostalias])"
	print "This tool can be used to publish files or plain-text on the web."
	print "When no arguments or options are given, publish reads text from stdin"
	print "until EOF, then puts all the text on pastebin and returns the link."
	print "With file arguments, publish can be used to publish files online to"
	print "a given server or to a presaved one using the conf file"
	print "Furthermore, the following options can be used:\n"
	print "%-15s%s"% ("Options",	"Meaning")
	for key in func_dict.keys():
		print "%-15s%s" % (func_dict[key].option, func_dict[key].explanation)

	if(postfunc != None):
		postfunc(postargs)

def rnd_str(length):
	result = ""
	alphabet = "abcdefghijklmnopqrstuvwxyz"
	for i in range(length):
		result += random.choice(alphabet)
	return result

if __name__ == '__main__':
	main()
