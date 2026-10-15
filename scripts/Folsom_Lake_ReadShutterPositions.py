# required imports to create the OpValue return object.
from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants

def initRuleScript(currentRule, network):
	"""Initialize this scripted rule, disabling it if Water Quality is not running.

	Parameters
	----------
	currentRule : object
		HEC-ResSim scripted rule object being initialized.
	network : object
		HEC-ResSim network object, used to query the current run's Water
		Quality (WQ) configuration.

	Returns
	-------
	int
		``Constants.TRUE``, unconditionally.

	Notes
	-----
	This rule depends on Water Quality results (the penstock port
	assignments in runRuleScript reference TCD port configuration). If WQ
	is not enabled for the current run, the rule is force-disabled via
	``setEvalRule(False)`` and a warning is printed, regardless of whether
	the rule was otherwise active or already disabled, so it never attempts
	to reference WQ data that will not exist for this simulation. This
	matches the WQ-gating pattern used in the EID/Muni/P1-P3 rule scripts
	elsewhere in this project; unlike the plain template version of this
	script (which only returns ``Constants.TRUE`` with no WQ check), this
	variant has that gating logic implemented.
	"""

	# return Constants.TRUE if the initialization is successful
	# and Constants.FALSE if it failed.  Returning Constants.FALSE
	# will halt the compute.
	
	wqRun = network.getRssRun().getWQRun()

	# Handle case where rule is active or disable but WQ is not being run
	if not wqRun:
		currentRule.setEvalRule(False)
		network.getRssRun().printWarningMessage("Warning: Scripted rule " + currentRule.getName() + 
			" references Water Quality which is disabled for this simulation. Rule will be ignored.")

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
	Execution is skipped entirely (returns ``None`` immediately) if
	``currentRule.getEvalRule()`` is false -- e.g. because initRuleScript
	disabled the rule due to WQ being off, or because the rule was
	otherwise deactivated elsewhere. When the rule is active, only the P1,
	P2, and P3 active-port assignments are actually implemented (``TCD1``,
	``TCD2``, ``TCD3`` are referenced here without any definition or import
	in this file, so they are assumed to be objects available in the
	HEC-ResSim scripting namespace at runtime, similar to how
	``RunTimeStep`` is used unimported in the Muni rule script). The
	remaining commented-out lines describing flow assignments
	(``p2Flow``, ``p3Flow``) and additional port assignments (``p2ActivePort``,
	``p3ActivePort``) are not implemented; unlike the three executable
	lines above them, these also use inconsistent naming (lowercase
	``p2ActivePort`` vs. the executable lines' ``"P2_active_port"`` string
	literal), which may simply reflect draft/placeholder naming never
	finalized. No penstock flow values are read or set anywhere in this
	function; only ports are assigned.
	"""

	evalRule = currentRule.getEvalRule()
	if not evalRule:
	    return None

	# Set Global time series values to represent
	# flows through penstocks and active penstock ports

	# Assign each penstock's active TCD port from its corresponding global
	# variable; TCD1/TCD2/TCD3 are assumed to be pre-existing objects in
	# the scripting namespace rather than anything defined in this file.
	TCD1.port = network.getGlobalVariable("P1_active_port")
	TCD2.port = network.getGlobalVariable("P2_active_port")
	TCD3.port = network.getGlobalVariable("P3_active_port")
	# GLOBAL.p2Flow.currentValue = read from external
	# GLOBAL.p2ActivePort = = read from external
	# GLOBAL.p3Flow.currentValue = read from external
	# GLOBAL.p3ActivePort = = read from external
	
	# return "None" to have no effect on the compute
	return None