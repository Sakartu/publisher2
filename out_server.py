class out_server:
	def __init__(self, location, url_prefix, password="", port=22):
		self.location = location
		(self.username, rest) = location.split('@')
		(self.hostname, self.remotedir) = rest.split(':')
		self.port = port
		self.url_prefix = url_prefix
		self.password = password
