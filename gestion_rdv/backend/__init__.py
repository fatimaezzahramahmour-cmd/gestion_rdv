# Allow type checker / Pylance to skip missing-module errors in editors
# (runtime still imports when available).
# pyright: reportMissingModuleSource=false
try:
	import pymysql
	pymysql.install_as_MySQLdb()
except Exception:
	# pymysql isn't available in this environment (editor/analysis). Skip.
	pass
