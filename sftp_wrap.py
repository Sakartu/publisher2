import os
import paramiko

def put(sftp, filepath, remotedir):
	#if filepath is a file, send only the file (no subdirs)
	if os.path.isfile(filepath):
		if os.path.isabs(filepath):
			pass
		else:
			pass
		out_path = os.path.join(remotedir, os.path.basename(filepath))
		#create subdirectories
		make_remote_dirs(sftp, os.path.dirname(out_path))
		sftp.put(filepath, out_path)
	else:
		#it's a dir, so we recursively send.
		paths = os.listdir(filepath)
		for p in paths:
			p = os.path.join(filepath, p)
			put(sftp, p, remotedir)

def make_remote_dirs(sftp, dirname):
	splits = [dirname]
	(head, tail) = os.path.split(dirname)
	while ((head, tail) != ("/", "") and (head, tail) != ("", "")):
		splits.append(head)
		(head, tail) = os.path.split(head)
	for path in reversed(splits):
		print "making dir %s" % path
		try:
			sftp.mkdir(path)
		except Exception, e:
			pass
