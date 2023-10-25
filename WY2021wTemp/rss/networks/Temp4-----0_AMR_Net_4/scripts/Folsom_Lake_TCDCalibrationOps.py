# required imports to create the OpValue return object.
from hec.rss.model import OpValue
from hec.rss.model import OpRule
from hec.script import Constants
#from java.lang import double

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
	return Constants.TRUE


# runRuleScript() is the entry point that is called during the
# compute.
#
# currentRule is the rule that holds this script
# network is the ResSim network
# currentRuntimestep is the current Run Time Step
def runRuleScript(currentRule, network, currentRuntimestep):

	# Set Global time series values to represent
	# flows through penstocks and active penstock ports

	gVarPairs = [
		("P1_specified_flow", "P1_flow_calib"),
		("P2_specified_flow", "P2_flow_calib"),
		("P3_specified_flow", "P3_flow_calib"),
		("P1_active_port", "p1__active_port_calib"),
		("P2_active_port", "p2__active_port_calib"),
		("P3_active_port", "p3__active_port_calib")]

	# GLOBAL: Penstock 1 Flow currentValue = read from external, etc.
	for pair in gVarPairs:
		# inVar = network.getGlobalVariable(pair[1])
		inVar = network.getGlobalVariable("P1_flow_calib")
		# outVar = network.getGlobalVariable(pair[0])
		outVar = network.getGlobalVariable("P1_specified_flow")
	
		passVal = inVar.getCurrentValue(currentRuntimestep)
		print "Invar is a " + str(type(inVar))
		print "Outvar is a " + str(type(outVar))
		print "Retrived value = (" + str(type(passVal)) +")"+ str(passVal)
		outVar.setCurrentValue(currentRuntimestep, double(passVal))

	# GLOBAL.p1ActivePort.currentValue = read from external, etc.
	# return "None" to have no effect on the compute
	return None
