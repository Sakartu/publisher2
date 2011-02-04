#!/usr/bin/python
import urllib
from sys import argv
from sys import stdin
import os
import getopt
import ConfigParser
import subprocess

'''
A litle program to publish files to the internet.
It can tar/zip before sending, use preprogrammed
hosts, print a link to the file and use an url
shortener to return a small url

v1.0	can upload files using scp, use a default 
		configfile or a specified one, print the 
		public url based on configparams and 
		short it if necessary

v1.1	can tar and/or zip files

v1.1.1	added support for verbose mode

v1.2	can tar and/or zip files without output

v1.3	can use default server from config when
		no destination provided

v1.4	can now handle multiple input files

v1.5	will put piped in text into pastebin and 
		return the link

1.5.1	fixed bug with conf_file, it wouldn't 
		look in the right place

1.6		if -s is used, with a website as the only 
		argument it will shorten it and return 
		the short url

1.6.1	just grouped a bit more code in methods

TODO
- fix multiple files upload with spaces
- maybe change some file access functions to os.path.*
- Add long-style cmdline options (such as --help)
- Exception handling
- Docstrings
- copy url directly to pastebuffer after creation (quite hard, needs external libs)
- make it windows compatible (hard: no tools)
- maybe change the pastebin functionality to work with "publish -" instead of "publish"
- catch keyboard interrupts like ^c and exit gracefully

coded by Sakartu for 0

'''
TEMP_PATH = "/tmp/publisher/"	#directory used to create intermediary files

has_opt = False					#do we have cmdline options
options = "stzrRc:Tpvoh"		#the possible cmdline options
shorten_url = False				#do we shorten the url after we're done?
tar_result = False				#do we tar the file(s) to send before we send it?
zip_result = False				#do we zip the file(s) to send before we send it?
recursive_send = False			#do we recurse into directories or not?
pastebin = False				#do we parse piped input to pastebin?
test_run = False				#is this a test run?
conf_file = "/etc/publish.conf"	#the configfile to use
conf = None						#the ConfigParser to use
verbose = False					#are we in verbose mode?
handle_mul_as_one = False		#handle multiple inputfiles as one

def main():
	global to_key

	#if we have no arguments, we read from stdin and assume the code piped in needs pastebinning
	if(len(argv) == 1):
		pastebin(stdin)
		exit(0)

	#parse arguments and options
	(from_paths, to_path) = parse_args(argv)

	#parse the configuration file
	parse_conf()
	#check to see if the to_path is set, if not, try to use the default in the conf
	if(len(to_path) < 1):
		if(conf.has_option("defaults", "server")):
			to_path = conf.get("defaults", "server")
		else:
			print "No destination given as argument and no default specified in conf, aborting!"
			usage()
			exit(-1)

	#if the first argument is just a URL, shorten it and return
	if(shorten_url and len(from_paths) == 1 and len(from_paths[0]) > 4 and from_paths[0][0:4] == "http"):
		if(conf.has_option("bit.ly", "username") and conf.has_option("bit.ly", "api_key")):
			url = url_shortener(from_paths[0], conf.get("bit.ly", "username"), conf.get("bit.ly", "api_key"))
			print "Short Url is: " + url,
			exit(0)
		else:
			print "Want to shorten url, but no bit.ly username or api key in conf!",
			exit(0)

	print "Sending from: " + str(from_paths) + "\nTo: " + to_path

	#we now have a function list of everything we're supposed to do before sending
	#we first have to see whether the destination is a nice path, or a previously saved one
	to_key = ""
	if(conf.has_option("servers", to_path)):
		to_key = to_path
		to_path = conf.get("servers", to_key)
	
	#find out if we can actually read the files to send
	check_access(from_paths)
	
	#usually, we handle multiple inputfiles one by one
	if(not handle_mul_as_one):
		for from_path in from_paths:
			#we also want to find out what the filename is that we're sending, to create a nice url afterwards
			if(from_path[-1] is not "/"):
				#so no directory
				file_name = from_path[from_path.rfind(os.sep) + 1:]
			else:
				if(not (tar_result or zip_result)):
					part = from_path[from_path[:-1].rfind(os.sep) + 1:]
				else:
					part = from_path[from_path[:-1].rfind(os.sep) + 1:-1]
				file_name = (part if (part is not "") else from_path)

			file_name, from_path = compact(from_paths, to_path, file_name)


			#send file
			scp_string = "scp " + ("-r " if recursive_send else "") + from_path + " " + to_path
			log("Executing: " + str(scp_string) + "\nIn: " + os.getcwd())
			if(not test_run):
				if(verbose):
					subprocess.call(scp_string, shell=True)
				else:
					subprocess.call(scp_string, stdout=open(os.devnull, "w"), stderr=subprocess.STDOUT, shell=True)
			
			#create url
			if(conf.has_option("locations", to_key)):
				url = conf.get("locations", to_key) + file_name
				print "Url is: " + url
				if(shorten_url and conf.has_option("bit.ly", "username") and conf.has_option("bit.ly", "api_key")):
					url = url_shortener(url, conf.get("bit.ly", "username"), conf.get("bit.ly", "api_key"))
					print "Short Url is: " + url
	else:
		#user wants us to handle all inputs and upload just one file (with either tar or zip)
		#find the filename of the first file, to use as filename for the file to send
		from_path = from_paths[0]
		if(from_path[-1] is not "/"):
			#so no directory
			file_name = from_path[from_path.rfind(os.sep) + 1:]
		else:
			part = from_path[from_path[:-1].rfind(os.sep) + 1:-1]
			file_name = (part if (part is not "") else from_path)

		file_name, from_path = compact(from_paths, to_path, file_name)

		#send file
		scp_string = "scp " + ("-r " if recursive_send else "") + from_path + " " + to_path
		log("Executing: " + str(scp_string) + "\nIn: " + os.getcwd())
		if(not test_run):
			if(verbose):
				subprocess.call(scp_string, shell=True)
			else:
				subprocess.call(scp_string, stdout=open(os.devnull, "w"), stderr=subprocess.STDOUT, shell=True)
		
		#create url
		if(conf.has_option("locations", to_key)):
			url = conf.get("locations", to_key) + file_name
			print "Url is: " + url
			if(shorten_url and conf.has_option("bit.ly", "username") and conf.has_option("bit.ly", "api_key")):
				url = url_shortener(url, conf.get("bit.ly", "username"), conf.get("bit.ly", "api_key"))
				print "Short Url is: " + url


def compact(from_paths, to_path, file_name):
	global TEMP_PATH
	#tar and/or zip if necessary
	current_dir = os.getcwd()
	if(tar_result or zip_result):
		prepare_temp_dir()
	if(tar_result and zip_result):
		current_dir = os.getcwd()
		file_name, from_path = tar_files(from_paths, to_path, file_name)
		os.chdir(TEMP_PATH)
		file_name, from_path = zip_files([file_name], to_path, file_name, TEMP_PATH)
		os.chdir(current_dir)
	elif (tar_result):
		file_name, from_path = tar_files(from_paths, to_path, file_name)
	elif (zip_result):
		file_name, from_path = zip_files(from_paths, to_path, file_name)
	else:
		from_path = reduce(lambda x, y : x + " " + y, from_paths)
	return file_name, from_path

def zip_files(from_paths, to_path, file_name, cwd=os.getcwd()):
	global recursive_send, test_run
	print "Zipping..."
	zip_file = TEMP_PATH + file_name + ".zip "
	from_path = reduce((lambda x, y: x + " " + y), from_paths)
	zip_string = "zip " + ("-r " if recursive_send else "") + zip_file + from_path
	log("Executing: " + zip_string + "\nin: " + str(cwd))
	#zipfile shouldn't already exist
	if(os.access(file_name + ".zip", os.F_OK)):
		log("Removing existing zipfile " + zip_file)
		os.remove(file_name + ".zip")
	if(not test_run):
		if(verbose):
			subprocess.call(zip_string, cwd=cwd, shell=True)
		else:
			subprocess.call(zip_string, stdout=open(os.devnull, "w"), stderr=subprocess.STDOUT, cwd=cwd, shell=True)
	file_name += ".zip"
	from_path = TEMP_PATH + file_name
	return (file_name, from_path)

def tar_files(from_paths, to_path, file_name, cwd=os.getcwd()):
	global test_run 
	print "Tarring..."
	tar_file = TEMP_PATH + file_name + ".tar "
	from_path = reduce((lambda x, y: x + " " + y), from_paths)
	tar_string = "tar " + "-cf " + tar_file + from_path
	log("Executing: " + str(tar_string) + "\nin: " + str(cwd))
	#tarfile shouldn't already exist
	if(os.access(tar_file, os.F_OK)):
		log("Removing existing tarfile " + tar_file)
		os.remove(tar_file)

	if(not test_run):
		if(verbose):
			subprocess.call(tar_string, cwd=cwd, shell=True)
		else: 
			subprocess.call(tar_string, stdout=open(os.devnull, "w"), stderr=subprocess.STDOUT, cwd=cwd, shell=True)
	file_name += ".tar"
	from_path = TEMP_PATH + file_name
	return (file_name, from_path)

def check_access(from_paths):
	for from_path in from_paths:
		if(not os.access(from_path, os.F_OK)): 
			print "Unable to read " + from_path + ", file does not exist!"
			exit(-1)
		if(not os.access(from_path, os.R_OK)):
			print "Unable to read " + from_path + ", permission denied!"
			exit(-1)

def parse_conf():
	global conf
	conf = ConfigParser.SafeConfigParser()
	log("Looking for conf file in " + conf_file)
	if(os.access(conf_file, os.F_OK) and os.access(conf_file, os.W_OK)):
		conf.read(conf_file)
	else:
		print "No configfile found, aborting!"
		exit(-1)
	
def parse_args(argv):
	global has_opt, options, zip_result, tar_result
	optlist, args = getopt.gnu_getopt(argv[1:], options)
	if(len(optlist) > 0):
		has_opt = True

	for o, a in optlist:
		if(o[1:] in functions):
			functions[o[1:]](a)
	
	#special case: if we have a -o, a -z or -t should have been set as well
	#if this is not the case, use tar as a default fallback
	if(handle_mul_as_one and not (zip_result or tar_result)):
		print "-o specified without -z or -t, defaulting to -t!"
		tar_result = True

	from_paths, to_path = "", ""
	if(len(args) > 0):
		#from_paths should always be the first one upto the second last one
		if(len(args) == 1):
			from_paths = args
		else:
			from_paths = args[0:-1]
		log("Setting from_paths to " + str(from_paths))
		#to_path is only the second to last argument if there are more than 1 args 
		if(len(args) > 1):
			to_path = args[-1]
			log("Setting to_path to " + str(to_path))

	return (from_paths, to_path)

def url_shortener(long_url, login_user, api_key):
	try:
		encoded_long_url = urllib.quote_plus(long_url)
		url="http://api.bit.ly/v3/shorten?longURL=%s&login=%s&apiKey=%s&format=txt" % (encoded_long_url, login_user, api_key)
		request = urllib.urlopen(url)
		responde = request.read()
		request.close()
		return responde

	except IOError, e:
		pass

def pastebin(file_content):
	print "Reading from stdin for output to pastebin..."
	print "If nothing is piped in, use ^d^d after typing to start uploading."
	url = "http://pastebin.com/api_public.php"
	#put all the lines of input toghether in one string
	lines = ""
	for line in file_content:
		#used to be lines = reduce(lambda x, y : x + y, file_content), but doesn't work when file_content is empty
		lines = lines + line
	if(len(lines) > 0):
		print "Uploading..."
		data = urllib.urlencode({"paste_code" : lines})
		request = urllib.urlopen(url, data)
		response = request.read()
		request.close()
		print "Done!"
		print "Pastebin url is: " + response
	else:
		usage()
		exit(0)

def prepare_temp_dir():
	if(not (os.access(TEMP_PATH, os.F_OK) and os.access(TEMP_PATH, os.W_OK))):
		log("Preparing directory \"" + TEMP_PATH + "\" for writing")
		os.makedirs(TEMP_PATH)

def opt_shorten_url(arg):
	global shorten_url
	shorten_url = True
	
def opt_tar_result(arg):
	global tar_result
	tar_result = True

def opt_zip_result(arg):
	global zip_result
	zip_result = True

def opt_pastebin(arg):
	global pastebin
	pastebin = True

def opt_recursive_send(arg):
	global recursive_send
	recursive_send = True

def opt_conf_file(arg):
	global conf_file
	if(len(arg) > 0):
		conf_file = arg
	
def opt_test_run(arg):
	global test_run
	test_run = True

def opt_verbose(arg):
	global verbose
	verbose = True

def opt_handle_mul_as_one(args):
	global handle_mul_as_one
	handle_mul_as_one = True

def opt_help(args):
	usage()
	exit(0)

def usage():
	print "Usage: publish [options] [(file/dir)+] ([[user@]host] | [hostalias])"
	print "This tool can be used to publish files or plain-text on the web."
	print "When no arguments or options are given, publish reads text from stdin"
	print "until EOF, then puts all the text on pastebin and returns the link."
	print "With file arguments, publish can be used to publish files online to"
	print "a given server or to a presaved one using the conf file"
	print "Furthermore, the following options can be used:\n"
	print "%-15s%s"% ("Options",	"Meaning")
	print "%-15s%s"% ("-s",			"Shorten url using bit.ly")
	print "%-15s%s"% ("-t",			"Tar file/dir before sending")
	print "%-15s%s"% ("-z",			"Zip file/dir before sending")
	print "%-15s%s"% ("-T",			"Test run; build all the commands but don't execute them, useful with -v")
	print "%-15s%s"% ("-r or -R",	"Handle directories recursive")
	print "%-15s%s"% ("-c <file>",	"Use different configfile")
	print "%-15s%s"% ("-o",			"Create one big input file, must be used with -z and/or -t")
	print "%-15s%s"% ("-h",			"Show this help")


def log(message):
	global verbose
	if(verbose):
		print message


functions = {'s' : opt_shorten_url,
			 't' : opt_tar_result,
			 'z' : opt_zip_result,
			 #'p' : opt_pastebin,
			 'r' : opt_recursive_send,
			 'R' : opt_recursive_send,
			 'c' : opt_conf_file,
			 'T' : opt_test_run,
			 'v' : opt_verbose,
			 'o' : opt_handle_mul_as_one,
			 'h' : opt_help
			 }

if __name__ == "__main__":
	main()
	
