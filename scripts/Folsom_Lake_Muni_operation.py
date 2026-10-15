# required imports to create the OpValue return object.
from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants

def initRuleScript(currentRule, network):
	"""Perform one-time setup for this scripted rule before the compute runs.

	Parameters
	----------
	currentRule : object
		HEC-ResSim scripted rule object that holds this script.
	network : object
		HEC-ResSim network object for the current compute.

	Returns
	-------
	int
		``Constants.TRUE`` if initialization succeeded, or
		``Constants.FALSE`` if it failed. Returning ``Constants.FALSE``
		halts the compute.

	Notes
	-----
	This initialization function is optional within the HEC-ResSim
	scripted-rule framework; use it to set up tables or other state that
	only needs to be computed once per simulation, rather than recomputing
	it on every call to runRuleScript.
	"""
	# return Constants.TRUE if the initialization is successful
	# and Constants.FALSE if it failed.  Returning Constants.FALSE
	# will halt the compute.
	return Constants.TRUE


def runRuleScript(currentRule, network, currentRuntimestep):
	"""Evaluate this scripted rule for the current time step.

	This is the entry point called by HEC-ResSim during the compute, once
	per time step, for as many iterations as the solver requires.

	Parameters
	----------
	currentRule : object
		HEC-ResSim scripted rule object that holds this script.
	network : object
		HEC-ResSim network object for the current compute.
	currentRuntimestep : object
		Current simulation Run Time Step being evaluated.

	Returns
	-------
	OpValue or None
		An Operation Value describing the rule's decision for this time
		step, or ``None`` to have no effect on the compute.

	Notes
	-----
	This is a template/skeleton implementation: the OpValue returned here
	is a placeholder maximum-flow specification of 1000 and is intended to
	be replaced with the rule's actual decision logic. The OpValue's
	``init`` call takes a type and a value; type must be one of
	``OpRule.RULETYPE_MAX`` (maximum flow), ``OpRule.RULETYPE_MIN``
	(minimum flow), or ``OpRule.RULETYPE_SPEC`` (specified flow).
	"""

	# create new Operation Value (OpValue) to return
	opValue = OpValue()

	# add your code here

	# set type and value for OpValue
	#  type is one of:
	#  OpRule.RULETYPE_MAX  - maximum flow
	#  OpRule.RULETYPE_MIN  - minimum flow
	#  OpRule.RULETYPE_SPEC - specified flow
	opValue.init(OpRule.RULETYPE_MAX, 1000)

	# return the Operation Value.
	# return "None" to have no effect on the compute
	return opValue