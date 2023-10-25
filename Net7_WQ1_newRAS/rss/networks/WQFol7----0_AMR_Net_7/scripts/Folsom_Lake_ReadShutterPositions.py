# required imports to create the OpValue return object.
from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants

#
# initialization function. optional.
#
# set up tables and other things that only need to be performed once during
# the compute.
#
# currentRule is the rule that holds this script
# network is the ResSim network
#
#
def initRuleScript(currentRule, network):
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


# runRuleScript() is the entry point that is called during the
# compute.
#
# currentRule is the rule that holds this script
# network is the ResSim network
# currentRuntimestep is the current Run Time Step
def runRuleScript(currentRule, network, currentRuntimestep):

	evalRule = currentRule.getEvalRule()
	if not evalRule:
	    return None

	# Set Global time series values to represent
	# flows through penstocks and active penstock ports

	TCD1.port = network.getGlobalVariable("P1_active_port")
	TCD2.port = network.getGlobalVariable("P2_active_port")
	TCD3.port = network.getGlobalVariable("P3_active_port")
	# GLOBAL.p2Flow.currentValue = read from external
	# GLOBAL.p2ActivePort = = read from external
	# GLOBAL.p3Flow.currentValue = read from external
	# GLOBAL.p3ActivePort = = read from external
	
	# return "None" to have no effect on the compute
	return None
