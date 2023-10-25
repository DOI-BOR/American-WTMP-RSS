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
	return Constants.TRUE


# runRuleScript() is the entry point that is called during the
# compute.
#
# currentRule is the rule that holds this script
# network is the ResSim network
# currentRuntimestep is the current Run Time Step
def runRuleScript(currentRule, network, currentRuntimestep):

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
