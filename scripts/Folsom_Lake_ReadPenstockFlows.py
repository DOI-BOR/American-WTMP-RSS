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
	None
		Always returns ``None``, which has no effect on the compute.

	Notes
	-----
	This is a template/skeleton implementation: the intended behavior
	(setting global time-series values for penstock flows p1Flow, p2Flow,
	and p3Flow from an external source, presumably to drive the
	corresponding P1/P2/P3 rule scripts elsewhere in this project) is
	described only in the commented-out pseudocode below and has not
	actually been implemented. As written, this function has no effect:
	it does not read or set any global variables, and always returns
	``None``.
	"""

	# Set Global time series values to represent
	# flows through penstocks and active penstock ports

	# GLOBAL.p1Flow.currentValue = read from external
	# GLOBAL.p2Flow.currentValue = read from external
	# GLOBAL.p3Flow.currentValue = read from external
	
	# return "None" to have no effect on the compute
	return None