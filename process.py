class process:
	def __init__(self, run, args, stage, option, explanation):
		self.run = run
		self.args = args
		self.option = option
		self.explanation = explanation
		self.stage = stage

	def __str__(self):
		return str(self.option) + " : " + str(self.explanation) + " : " + str(self.run) + " : " + str(self.args)

	def __repr__(self):
		return str(self.option) + " : " + str(self.explanation) + " : " + str(self.run) + " : " + str(self.args) + "\n"
